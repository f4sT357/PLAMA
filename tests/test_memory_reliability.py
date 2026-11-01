"""Memory safety regressions. Run with: python -m pytest -q tests."""
import asyncio
import json
import sys
import types

import pytest

# Fake the heavyweight optional integration libraries; tests exercise persistence
# and session bookkeeping without downloading any LLM/embedding model.
class FakeVectors(list):
    def tolist(self):
        return list(self)

class FakeEmbedding:
    def __init__(self, *args, **kwargs):
        pass

    def encode(self, texts, normalize_embeddings=True):
        return FakeVectors([[float(sum(bytearray(text.encode("utf-8")))), float(len(text))] for text in texts])

class FakeCollection:
    def __init__(self):
        self.documents = {}

    def count(self):
        return len(self.documents)

    def add(self, ids, embeddings, documents, metadatas):
        for i, emb, doc in zip(ids, embeddings, documents):
            if i in self.documents:
                raise ValueError("duplicate ID")
            self.documents[i] = (emb, doc)

    def query(self, query_embeddings, n_results, include):
        emb = query_embeddings[0]
        matched = sorted(
            ((0.0 if value[0] == emb else 1.0, key) for key, value in self.documents.items())
        )[:n_results]
        return {"ids": [[key for _, key in matched]],
                "distances": [[dist for dist, _ in matched]]}

    def delete(self, ids):
        for key in ids:
            self.documents.pop(key, None)

class FakeChromaClient:
    def __init__(self, *args, **kwargs):
        self.collections = {}

    def get_or_create_collection(self, name):
        return self.collections.setdefault(name, FakeCollection())

    def get_collection(self, name):
        return self.collections[name]

    def delete_collection(self, name):
        self.collections.pop(name, None)

chroma = types.ModuleType("chromadb")
chroma.ClientAPI = object
chroma.PersistentClient = FakeChromaClient
config = types.ModuleType("chromadb.config")
config.Settings = lambda **kwargs: None
chroma.config = config
sys.modules["chromadb"] = chroma
sys.modules["chromadb.config"] = config
sentence_transformers = types.ModuleType("sentence_transformers")
sentence_transformers.SentenceTransformer = FakeEmbedding
sys.modules["sentence_transformers"] = sentence_transformers

import memory_manager as mod
from models import MemorySchema, MessageEntry, ShortTermMemory


@pytest.fixture
def mm(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(mod, "MEMORY_JSON", tmp_path / "memory.json")
    monkeypatch.setattr(mod, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(mod, "CORPUS_DIR", tmp_path / "corpus")
    manager = mod.MemoryManager()
    manager.init()
    return manager


def test_invalid_json_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "memory.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(mod, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(mod, "MEMORY_JSON", path)
    monkeypatch.setattr(mod, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(mod, "CORPUS_DIR", tmp_path / "corpus")
    with pytest.raises(RuntimeError):
        mod.MemoryManager().init()
    assert path.read_text(encoding="utf-8") == "{broken"


def test_sessions_are_isolated_and_persistent(mm):
    a = mm.new_session()
    mm.add_message(a, "user", "first session")
    b = mm.new_session()
    mm.add_message(b, "user", "second session")
    assert [m.content for m in mm.get_recent_messages(a)] == ["first session"]
    assert [m.content for m in mm.get_recent_messages(b)] == ["second session"]
    assert not mm.session_exists("nonexistent")
    reloaded = mod.MemoryManager()
    reloaded.init()
    assert reloaded.get_recent_messages(a)[0].content == "first session"


def test_consolidation_is_idempotent_and_keeps_raw_messages(mm):
    sid = mm.new_session()
    mm.add_message(sid, "user", "use a 42T ring")
    snapshot = mm.get_pending_messages(sid)[-1].id
    mm.add_message(sid, "user", "maybe 38T later")
    async def consolidate():
        return await mm.consolidate_session(
            sid, summary="gearing discussion",
            extracted_facts=[{"content": "Uses a 42T ring", "category": "preferences"}],
            model_used="test-4b",
            last_snapshot_message_id=snapshot
        )
    result = asyncio.run(consolidate())
    assert result["added"] == 1
    assert [m.content for m in mm.get_pending_messages(sid)] == ["maybe 38T later"]
    assert len(mm.get_recent_messages(sid)) == 2
    again = asyncio.run(consolidate())
    assert again["already_consolidated"] is True
    assert len(mm.get_facts()) == 1


def test_legacy_short_term_is_migrated(tmp_path, monkeypatch):
    legacy = MemorySchema(short_term=ShortTermMemory(
        current_session_id="old-session",
        messages=[MessageEntry(role="user", content="old conversation")]
    ))
    path = tmp_path / "memory.json"
    path.write_text(legacy.model_dump_json(by_alias=True), encoding="utf-8")
    monkeypatch.setattr(mod, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(mod, "MEMORY_JSON", path)
    monkeypatch.setattr(mod, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(mod, "CORPUS_DIR", tmp_path / "corpus")
    manager = mod.MemoryManager()
    manager.init()
    assert manager.get_recent_messages("old-session")[0].content == "old conversation"
    assert (tmp_path / "memory.json.bak").exists()


def test_invalid_fact_does_not_advance_cursor(mm):
    sid = mm.new_session()
    mm.add_message(sid, "user", "hello")
    snapshot = mm.get_pending_messages(sid)[-1].id
    with pytest.raises(Exception):
        asyncio.run(mm.consolidate_session(
            sid, summary="bad", extracted_facts=[{"content": "bad", "category": "nonsense"}],
            last_snapshot_message_id=snapshot
        ))
    assert len(mm.get_pending_messages(sid)) == 1
