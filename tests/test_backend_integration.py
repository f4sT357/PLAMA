"""Backend integration of session HTTP APIs and evidence-backed consolidation."""
import asyncio
import importlib
import json

import pytest

# Reuse lightweight Chroma / embeddings fakes.
from test_memory_reliability import mm  # noqa: F401
import memory_manager as mod


@pytest.fixture
def backend(mm, monkeypatch):
    # The import-time singleton must point to the isolated test database.
    monkeypatch.setattr(mod, "memory_manager", mm)
    import main
    monkeypatch.setattr(main, "memory_manager", mm)

    async def loaded(*args, **kwargs):
        return True

    async def fake_llm(url, model, messages, max_tokens=1500):
        prompt = messages[0]["content"]
        # The source message ID is present in a fixed user turn.
        mid = next(msg.id for msgs in mm.get_schema().session_messages.values() for msg in msgs
                   if "I prefer local model portability" in msg.content)
        return json.dumps({
            "summary": "User configuration",
            "facts": [{
                "content": "User prefers local model portability",
                "category": "preferences",
                "confidence": 0.8,
                "assertion_kind": "explicit",
                "evidence_message_ids": [mid],
                "evidence_quote": "I prefer local model portability"
            }]
        })

    monkeypatch.setattr(main.model_router, "ensure_model_loaded", loaded)
    monkeypatch.setattr(main, "_llm_complete", fake_llm)
    return main


def test_api_rejects_unknown_session(backend):
    import httpx

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=backend.app), base_url="http://test"
        ) as client:
            r = await client.get("/api/session/no-such-session")
            assert r.status_code == 404
            r = await client.post("/api/chat/stream", json={
                "session_id": "no-such-session", "message": "hello"
            })
            assert r.status_code == 404
    asyncio.run(run())


def test_api_consolidates_only_current_session(backend, mm):
    import httpx

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=backend.app), base_url="http://test"
        ) as client:
            sid = (await client.post("/api/session/new")).json()["session_id"]
            mm.add_message(sid, "user", "I prefer local model portability")
            other = (await client.post("/api/session/new")).json()["session_id"]
            mm.add_message(other, "user", "Unrelated conversation")
            response = await client.post(f"/api/session/{sid}/consolidate")
            assert response.status_code == 200, response.text
            assert response.json()["added"] == 1
            fact = mm.get_facts()[0]
            assert fact.source_session == sid
            assert fact.assertion_kind == "explicit"
            assert fact.evidence_quote == "I prefer local model portability"
            assert len(mm.get_pending_messages(sid)) == 0
            assert len(mm.get_pending_messages(other)) == 1
    asyncio.run(run())
