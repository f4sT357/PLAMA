"""
PLAMA v1.4 - MemoryManager
Handles:
  - memory.json persistence (MemorySchema v2.0)
  - ChromaDB semantic indexing via sentence-transformers
  - Fact deduplication (v1.4: semantic similarity check)
  - Mid-session consolidation trigger (v1.4)
  - TrustRegistry updates (v1.5 stubs present)
"""
from __future__ import annotations

import json
import logging
import re
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from models import (
    FactCategory,
    FactEntry,
    MemorySchema,
    MessageEntry,
    ModelTrustEntry,
    SessionEntry,
    ShortTermMemory,
    SourceType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MEMORY_DIR = Path(os.getenv("PLAMA_MEMORY_DIR", "./memory_data"))
MEMORY_JSON = MEMORY_DIR / "memory.json"
CHROMA_DIR = MEMORY_DIR / "chroma_store"
CORPUS_DIR = MEMORY_DIR / "corpus_store"

EMBEDDING_MODEL = os.getenv("PLAMA_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

# Deduplication threshold: cosine distance below this = duplicate
DEDUP_THRESHOLD = float(os.getenv("PLAMA_DEDUP_THRESHOLD", "0.12"))

# Mid-session consolidation trigger: consolidate when short_term exceeds N messages
MID_SESSION_CONSOLIDATE_THRESHOLD = int(os.getenv("PLAMA_MID_SESSION_THRESHOLD", "20"))

CHROMA_FACTS_COLLECTION = "plama_facts"
CHROMA_CORPUS_COLLECTION = "plama_corpus"


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

class MemoryManager:
    def __init__(self):
        self._schema: MemorySchema | None = None
        self._chroma: chromadb.ClientAPI | None = None
        self._embed_model: SentenceTransformer | None = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Call once at startup."""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        CORPUS_DIR.mkdir(parents=True, exist_ok=True)

        self._load_schema()
        self._init_chroma()
        self._load_embedding_model()
        logger.info("MemoryManager initialised. facts=%d sessions=%d",
                    len(self._schema.facts), len(self._schema.sessions))

    def _load_schema(self) -> None:
        if MEMORY_JSON.exists():
            # Fail closed: an unreadable file must never be replaced with empty memory.
            try:
                raw = json.loads(MEMORY_JSON.read_text(encoding="utf-8"))
                self._schema = MemorySchema.model_validate(raw)
            except Exception:
                logger.exception("Cannot read memory.json; leaving the original untouched")
                raise RuntimeError(
                    f"Memory database at {MEMORY_JSON} is invalid; restore a backup before starting"
                ) from None

            # One-time non-destructive migration of the legacy single-session buffer.
            legacy = self._schema.short_term
            if legacy.current_session_id and legacy.messages:
                self._schema.session_messages.setdefault(
                    legacy.current_session_id, list(legacy.messages)
                )
                self._schema.short_term = ShortTermMemory(
                    current_session_id=legacy.current_session_id
                )
                self._save_schema()
            logger.info("Loaded existing memory.json (schema %s)", self._schema.meta.schema_version)
            return

        self._schema = MemorySchema()
        self._save_schema()

    def _init_chroma(self) -> None:
        self._chroma = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        # Ensure collections exist
        self._chroma.get_or_create_collection(CHROMA_FACTS_COLLECTION)
        self._chroma.get_or_create_collection(CHROMA_CORPUS_COLLECTION)

    def _load_embedding_model(self) -> None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        self._embed_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model ready.")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_schema(self) -> None:
        self._schema.bump_updated()
        payload = self._schema.model_dump_json(by_alias=True, indent=2)
        # Validate before touching durable state.
        json.loads(payload)
        tmp = MEMORY_JSON.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if MEMORY_JSON.exists():
            shutil.copy2(MEMORY_JSON, MEMORY_JSON.with_suffix(".json.bak"))
        tmp.replace(MEMORY_JSON)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self._embed_model.encode(texts, normalize_embeddings=True).tolist()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def new_session(self) -> str:
        session_id = f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        # Never discard another session's pending messages.
        self._schema.session_messages[session_id] = []
        self._schema.session_consolidation_cursor[session_id] = 0
        self._schema.short_term.current_session_id = session_id
        self._schema.sessions.append(SessionEntry(
            id=session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        ))
        self._save_schema()
        logger.info("New session: %s", session_id)
        return session_id

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._schema.session_messages

    def add_message(
        self, session_id: str, role: str, content: str, model_used: str | None = None
    ) -> None:
        if not self.session_exists(session_id):
            raise ValueError(f"Unknown session: {session_id}")
        msg = MessageEntry(role=role, content=content, model_used=model_used)  # type: ignore[arg-type]
        self._schema.session_messages[session_id].append(msg)
        # Raw messages are intentionally not pruned. Consolidation is a derived view.
        self._save_schema()

    def get_recent_messages(self, session_id: str, n: int = 10) -> list[MessageEntry]:
        if not self.session_exists(session_id):
            raise ValueError(f"Unknown session: {session_id}")
        return self._schema.session_messages[session_id][-n:]

    def get_pending_messages(self, session_id: str) -> list[MessageEntry]:
        if not self.session_exists(session_id):
            raise ValueError(f"Unknown session: {session_id}")
        cursor = self._schema.session_consolidation_cursor.get(session_id, 0)
        return list(self._schema.session_messages[session_id][cursor:])

    def should_mid_consolidate(self, session_id: str) -> bool:
        return len(self.get_pending_messages(session_id)) >= MID_SESSION_CONSOLIDATE_THRESHOLD

    def get_current_session_id(self) -> str | None:
        return self._schema.short_term.current_session_id

    # ------------------------------------------------------------------
    # Fact management
    # ------------------------------------------------------------------

    def add_fact(
        self,
        content: str,
        category: FactCategory = "other",
        confidence: float = 0.7,
        source_type: SourceType = "inference",
        tags: list[str] | None = None,
        model_origin: str = "unknown",
        model_trust_score: float = 0.0,
        expires_at: str | None = None,
        session_id: str | None = None,
        assertion_kind: str = "unknown",
        evidence_message_ids: list[str] | None = None,
    ) -> FactEntry | None:
        """
        Add a fact after deduplication check.
        Returns None if considered duplicate.
        """
        # Semantic similarity does NOT imply equality. A changed number or a
        # negation must be retained, even if the embeddings are nearly identical.
        if self._is_duplicate(content):
            logger.info("Exact duplicate fact skipped")
            return None

        session_id = session_id or self._schema.short_term.current_session_id
        fact = FactEntry(
            content=content,
            category=category,
            confidence=min(confidence, 0.9),
            source_type=source_type,
            tags=tags or [],
            model_origin=model_origin,
            model_trust_score=model_trust_score,
            source_session=session_id,
            expires_at=expires_at,
            assertion_kind=assertion_kind,
            evidence_message_ids=evidence_message_ids or [],
        )
        self._schema.facts.append(fact)
        self._index_fact(fact)
        self._save_schema()
        logger.info("Fact added: id=%s category=%s", fact.id, fact.category)
        return fact

    def replace_fact(self, fact_id: str, new_content: str) -> FactEntry | None:
        """An explicit user correction supersedes but does not erase history."""
        previous = next((f for f in self._schema.facts if f.id == fact_id), None)
        if previous is None or previous.status != "active":
            return None
        content = new_content.strip()
        if not content:
            raise ValueError("Cannot replace a fact with empty content")
        now = datetime.now(timezone.utc).isoformat()
        correction = FactEntry(
            content=content,
            category=previous.category,
            confidence=0.9,
            source_type="explicit",
            assertion_kind="explicit",
            tags=list(previous.tags),
            valid_from=now,
            supersedes=[previous.id],
        )
        previous.status = "superseded"
        previous.valid_to = now
        previous.updated_at = now
        self._schema.facts.append(correction)
        self._index_fact(correction)
        self._save_schema()
        return correction

    def delete_fact(self, fact_id: str) -> bool:
        before = len(self._schema.facts)
        self._schema.facts = [f for f in self._schema.facts if f.id != fact_id]
        if len(self._schema.facts) < before:
            try:
                col = self._chroma.get_collection(CHROMA_FACTS_COLLECTION)
                col.delete(ids=[fact_id])
            except Exception as e:
                logger.warning("ChromaDB delete failed: %s", e)
            self._save_schema()
            return True
        return False

    def get_facts(self, source_type: str | None = None) -> list[FactEntry]:
        facts = self._schema.facts
        if source_type:
            facts = [f for f in facts if f.source_type == source_type]
        return facts

    @staticmethod
    def _lexical_terms(text: str) -> set[str]:
        """Conservative local lexical index; Japanese bigrams + ASCII words."""
        chunks = re.findall(r"[a-z0-9_]+|[\u3040-\u30ff\u3400-\u9fff]+", text.casefold())
        terms: set[str] = set()
        for chunk in chunks:
            if any(ord(char) > 127 for char in chunk):
                terms.update(chunk[i:i + 2] for i in range(max(0, len(chunk) - 1)))
                if len(chunk) == 1:
                    terms.add(chunk)
            else:
                terms.add(chunk)
        return terms

    @staticmethod
    def _fact_is_current(fact: FactEntry) -> bool:
        if fact.status != "active":
            return False
        if fact.expires_at:
            try:
                expiry = datetime.fromisoformat(fact.expires_at.replace("Z", "+00:00"))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                return expiry > datetime.now(timezone.utc)
            except ValueError:
                # Unknown expiry is not proof that a fact is still current.
                return False
        return True

    def search_facts(self, query: str, n_results: int = 5) -> list[FactEntry]:
        """Hybrid reciprocal-rank fusion; recover lexical matches if vector index fails."""
        if not query.strip() or n_results <= 0:
            return []
        candidates = {f.id: f for f in self._schema.facts if self._fact_is_current(f)}
        if not candidates:
            return []
        width = max(n_results * 5, 20)
        dense_ids: list[str] = []
        try:
            col = self._chroma.get_collection(CHROMA_FACTS_COLLECTION)
            if col.count() > 0:
                emb = self._embed([query])[0]
                result = col.query(
                    query_embeddings=[emb],
                    n_results=min(width, col.count()),
                    include=["distances"],
                )
                dense_ids = [fid for fid in result["ids"][0] if fid in candidates]
        except Exception as e:
            logger.warning("Vector index unavailable; lexical retrieval remains active: %s", e)

        query_terms = self._lexical_terms(query)
        lexical = []
        if query_terms:
            for fact in candidates.values():
                common = query_terms & self._lexical_terms(fact.content)
                if common:
                    lexical.append((len(common) / len(query_terms), fact.id))
        lexical.sort(key=lambda row: (-row[0], row[1]))
        lexical_ids = [fid for _, fid in lexical[:width]]

        scores: dict[str, float] = {}
        for ids in (dense_ids, lexical_ids):
            for i, fid in enumerate(ids):
                scores[fid] = scores.get(fid, 0.0) + 1.0 / (60 + i + 1)
        best = sorted(scores, key=lambda fid: (-scores[fid], fid))[:n_results]
        return [candidates[fid] for fid in best]

    def rebuild_chroma_index(self) -> int:
        """Rebuild ChromaDB from memory.json. Returns count of indexed facts."""
        try:
            self._chroma.delete_collection(CHROMA_FACTS_COLLECTION)
        except Exception:
            pass
        self._chroma.get_or_create_collection(CHROMA_FACTS_COLLECTION)

        facts = self._schema.facts
        if not facts:
            return 0

        batch_size = 64
        count = 0
        for i in range(0, len(facts), batch_size):
            batch = facts[i: i + batch_size]
            self._index_facts_batch(batch)
            count += len(batch)
        logger.info("Rebuilt ChromaDB index: %d facts", count)
        return count

    # ------------------------------------------------------------------
    # Consolidation (v1.4: called after session end OR mid-session trigger)
    # ------------------------------------------------------------------

    async def consolidate_session(
        self,
        session_id: str,
        summary: str,
        extracted_facts: list[dict],
        model_used: str = "unknown",
        last_snapshot_message_id: str | None = None,
    ) -> dict:
        """Commit derived facts while retaining all original messages."""
        if not self.session_exists(session_id):
            raise ValueError(f"Unknown session: {session_id}")
        messages = self._schema.session_messages[session_id]
        cursor = self._schema.session_consolidation_cursor.get(session_id, 0)
        if not last_snapshot_message_id:
            raise ValueError("Consolidation requires a stable message snapshot ID")
        idx = next((i for i, msg in enumerate(messages) if msg.id == last_snapshot_message_id), None)
        if idx is None:
            raise ValueError("Unknown snapshot message ID")
        if idx < cursor:
            return {"added": 0, "skipped_duplicates": 0, "session_id": session_id,
                    "already_consolidated": True}

        # Validate the entire model response before any facts are committed.
        if not isinstance(extracted_facts, list) or not isinstance(summary, str):
            raise ValueError("Invalid consolidation response")
        for raw in extracted_facts:
            if not isinstance(raw, dict) or not isinstance(raw.get("content"), str):
                raise ValueError("Invalid fact in consolidation response")
            FactEntry(
                content=raw["content"], category=raw.get("category", "other"),
                confidence=raw.get("confidence", 0.6),
            )

        added = skipped = 0
        trust_score = self._get_model_trust(model_used)
        for raw in extracted_facts:
            result = self.add_fact(
                content=raw["content"],
                category=raw.get("category", "other"),
                confidence=raw.get("confidence", 0.6),
                source_type="consolidated",
                tags=raw.get("tags", []),
                model_origin=model_used,
                model_trust_score=trust_score,
                session_id=session_id,
                assertion_kind=raw.get("assertion_kind", "unknown"),
                evidence_message_ids=raw.get("evidence_message_ids", []),
            )
            if result:
                added += 1
            else:
                skipped += 1

        for sess in self._schema.sessions:
            if sess.id == session_id:
                sess.summary = summary
                sess.message_count = idx + 1
                if model_used not in sess.models_used:
                    sess.models_used.append(model_used)
                # Only mark ended when the snapshot includes the last message.
                if idx + 1 == len(messages):
                    sess.ended_at = datetime.now(timezone.utc).isoformat()
                break

        self._schema.session_consolidation_cursor[session_id] = idx + 1
        self._save_schema()
        return {"added": added, "skipped_duplicates": skipped, "session_id": session_id}

    # ------------------------------------------------------------------
    # TrustRegistry helpers (v1.4: read/write; v1.5: full scoring)
    # ------------------------------------------------------------------

    def _get_model_trust(self, model_name: str) -> float:
        entry = self._schema.model_trust_registry.get(model_name)
        return entry.trust_score if entry else 1.0

    def record_model_output(self, model_name: str, bias_flagged: bool = False) -> None:
        """Update TrustRegistry after each model response. (v1.5 full scoring)"""
        if model_name not in self._schema.model_trust_registry:
            self._schema.model_trust_registry[model_name] = ModelTrustEntry()
        entry = self._schema.model_trust_registry[model_name]
        entry.total_outputs += 1
        if bias_flagged:
            entry.bias_flags += 1
        entry.recalculate_trust()
        self._save_schema()

    def get_trust_registry(self) -> dict[str, ModelTrustEntry]:
        return dict(self._schema.model_trust_registry)

    # ------------------------------------------------------------------
    # Full schema access
    # ------------------------------------------------------------------

    def get_schema(self) -> MemorySchema:
        return self._schema

    def get_core_profile(self) -> dict:
        return self._schema.core_profile.model_dump()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_duplicate(self, content: str, threshold: float = DEDUP_THRESHOLD) -> bool:
        """Only discard exact normalized duplicates, never corrections."""
        canonical = " ".join(content.casefold().split())
        return any(
            f.status == "active" and " ".join(f.content.casefold().split()) == canonical
            for f in self._schema.facts
        )

    def _index_fact(self, fact: FactEntry) -> None:
        try:
            col = self._chroma.get_collection(CHROMA_FACTS_COLLECTION)
            emb = self._embed([fact.content])[0]
            col.add(
                ids=[fact.id],
                embeddings=[emb],
                documents=[fact.content],
                metadatas=[{"category": fact.category, "source_type": fact.source_type}],
            )
        except Exception as e:
            logger.error("_index_fact error: %s", e)

    def _index_facts_batch(self, facts: list[FactEntry]) -> None:
        try:
            col = self._chroma.get_collection(CHROMA_FACTS_COLLECTION)
            texts = [f.content for f in facts]
            embs = self._embed(texts)
            col.add(
                ids=[f.id for f in facts],
                embeddings=embs,
                documents=texts,
                metadatas=[{"category": f.category, "source_type": f.source_type} for f in facts],
            )
        except Exception as e:
            logger.error("_index_facts_batch error: %s", e)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

memory_manager = MemoryManager()
