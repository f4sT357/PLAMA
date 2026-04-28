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
import os
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
            try:
                raw = json.loads(MEMORY_JSON.read_text(encoding="utf-8"))
                # Migrate v1.x → v2.0 by filling missing fields with defaults
                self._schema = MemorySchema.model_validate(raw)
                logger.info("Loaded existing memory.json (schema %s)", self._schema.meta.schema_version)
                return
            except Exception as e:
                logger.warning("Failed to parse memory.json: %s — starting fresh", e)
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
        tmp = MEMORY_JSON.with_suffix(".tmp")
        tmp.write_text(
            self._schema.model_dump_json(by_alias=True, indent=2),
            encoding="utf-8",
        )
        tmp.replace(MEMORY_JSON)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self._embed_model.encode(texts, normalize_embeddings=True).tolist()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def new_session(self) -> str:
        session_id = f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        self._schema.short_term = ShortTermMemory(current_session_id=session_id)
        self._schema.sessions.append(SessionEntry(
            id=session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        ))
        # Cap sessions at 100
        if len(self._schema.sessions) > 100:
            self._schema.sessions = self._schema.sessions[-100:]
        self._save_schema()
        logger.info("New session: %s", session_id)
        return session_id

    def add_message(self, role: str, content: str, model_used: str | None = None) -> None:
        msg = MessageEntry(role=role, content=content, model_used=model_used)  # type: ignore[arg-type]
        self._schema.short_term.messages.append(msg)
        # Enforce max_messages
        if len(self._schema.short_term.messages) > self._schema.short_term.max_messages:
            self._schema.short_term.messages = self._schema.short_term.messages[
                -self._schema.short_term.max_messages:
            ]
        # v1.4: mid-session consolidation trigger
        if len(self._schema.short_term.messages) >= MID_SESSION_CONSOLIDATE_THRESHOLD:
            logger.info("Mid-session threshold reached (%d messages); auto-consolidation pending",
                        len(self._schema.short_term.messages))
            # Flag is checked by caller (main.py); actual consolidation is async
        self._save_schema()

    def should_mid_consolidate(self) -> bool:
        return len(self._schema.short_term.messages) >= MID_SESSION_CONSOLIDATE_THRESHOLD

    def get_recent_messages(self, n: int = 10) -> list[MessageEntry]:
        return self._schema.short_term.messages[-n:]

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
    ) -> FactEntry | None:
        """
        Add a fact after deduplication check.
        Returns None if considered duplicate.
        """
        if self._is_duplicate(content):
            logger.info("Duplicate fact skipped: %r", content[:60])
            return None

        session_id = self._schema.short_term.current_session_id
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
        )
        self._schema.facts.append(fact)
        self._index_fact(fact)
        self._save_schema()
        logger.info("Fact added: id=%s category=%s", fact.id, fact.category)
        return fact

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

    def search_facts(self, query: str, n_results: int = 5) -> list[FactEntry]:
        """Semantic search over ChromaDB-indexed facts."""
        try:
            col = self._chroma.get_collection(CHROMA_FACTS_COLLECTION)
            if col.count() == 0:
                return []
            emb = self._embed([query])[0]
            results = col.query(
                query_embeddings=[emb],
                n_results=min(n_results, col.count()),
                include=["documents", "distances"],
            )
            ids = results["ids"][0]
            distances = results["distances"][0]
            id_score = dict(zip(ids, distances))
            # Return FactEntry objects in order
            matched = [f for f in self._schema.facts if f.id in id_score]
            matched.sort(key=lambda f: id_score.get(f.id, 1.0))
            return matched
        except Exception as e:
            logger.error("search_facts error: %s", e)
            return []

    def search_corpus(self, query: str, n_results: int = 5) -> dict:
        """
        Semantic search over the propaganda corpus.
        Returns the raw ChromaDB results (including distances).
        """
        try:
            col = self._chroma.get_collection(CHROMA_CORPUS_COLLECTION)
            if col.count() == 0:
                return {}
            emb = self._embed([query])[0]
            return col.query(
                query_embeddings=[emb],
                n_results=min(n_results, col.count()),
                include=["documents", "distances", "metadatas"],
            )
        except Exception as e:
            logger.error("search_corpus error: %s", e)
            return {}

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
    ) -> dict:
        """
        Write session summary and upsert consolidated facts.
        Called from main.py after LLM generates summary + fact extraction.
        """
        # Update session record
        for sess in self._schema.sessions:
            if sess.id == session_id:
                sess.ended_at = datetime.now(timezone.utc).isoformat()
                sess.summary = summary
                sess.message_count = len(self._schema.short_term.messages)
                if model_used not in sess.models_used:
                    sess.models_used.append(model_used)
                break

        added = 0
        skipped = 0
        trust_score = self._get_model_trust(model_used)

        for raw in extracted_facts:
            result = self.add_fact(
                content=raw.get("content", ""),
                category=raw.get("category", "other"),
                confidence=raw.get("confidence", 0.6),
                source_type="consolidated",
                tags=raw.get("tags", []),
                model_origin=model_used,
                model_trust_score=trust_score,
            )
            if result:
                added += 1
            else:
                skipped += 1

        # Clear short-term for next session
        self._schema.short_term.messages = []
        self._save_schema()

        logger.info("Consolidation done: added=%d skipped=%d(dup)", added, skipped)
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
        """
        v1.4 deduplication: embed the new content, query ChromaDB,
        if closest distance < threshold → duplicate.
        """
        try:
            col = self._chroma.get_collection(CHROMA_FACTS_COLLECTION)
            if col.count() == 0:
                return False
            emb = self._embed([content])[0]
            results = col.query(
                query_embeddings=[emb],
                n_results=1,
                include=["distances"],
            )
            if results["distances"] and results["distances"][0]:
                closest_dist = results["distances"][0][0]
                return closest_dist < threshold
        except Exception as e:
            logger.warning("Dedup check error: %s", e)
        return False

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
