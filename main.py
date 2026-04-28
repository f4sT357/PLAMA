"""
PLAMA v1.4 - FastAPI Backend
All v1.3 endpoints (unchanged) + v2.0 new endpoints.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from bias_checker import bias_checker
from memory_manager import memory_manager, MEMORY_DIR
from model_router import router as model_router, ModelConfig
from models import (
    BiasCheckRequest,
    BiasCheckResponse,
    ChatRequest,
    HealthResponse,
    ModelLoadRequest,
    N8nIngestRequest,
    NewSessionResponse,
    RouteQueryRequest,
    RouteQueryResponse,
    PlamaConfig,
    UpdateConfigRequest,
)
from config_manager import ConfigManager
from pipeline_ingest import pipeline_ingest
from prompt_builder import prompt_builder
from trust_registry import TrustRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("plama.main")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="PLAMA", version="2.0.0", description="Persistent Local AI Memory Adapter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

memory_manager.init()
config_manager = ConfigManager(MEMORY_DIR)

# Inject config manager into components
model_router.config_manager = config_manager
bias_checker.config_manager = config_manager
bias_checker.model_router = model_router

trust_registry = TrustRegistry(memory_manager)


@app.on_event("startup")
async def startup():
    # memory_manager already initialized above to get data_dir
    # Pre-initialize trust registry entries from router definitions
    for m in model_router.list_models():
        trust_registry.initialize_model(m.name, m.topic_tags, m.avoid_tags)
    
    # 初回起動時にモデルリストを取得
    await model_router.refresh_available_models(force=True)
    logger.info("PLAMA v2.0 ready with dynamic config and %d models found.", len(model_router.available_model_ids))


# ---------------------------------------------------------------------------
# Helper: call LM Studio (non-streaming)
# ---------------------------------------------------------------------------

async def _llm_complete(model_url: str, model_name: str, messages: list[dict], max_tokens: int = 1500) -> str:
    url = f"{model_url}/chat/completions"
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,  # タイムアウト回避のためストリーミングを使用
        "temperature": 0.2,
    }
    
    full_content = ""
    reasoning_content = ""
    
    try:
        # 接続のタイムアウトは短く、生成（読み取り）のタイムアウトは長く設定
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "): continue
                    if line == "data: [DONE]": break
                    
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"]
                        
                        # 通常の回答または思考ログを蓄積
                        if "content" in delta:
                            full_content += delta["content"]
                        if "reasoning_content" in delta:
                            reasoning_content += delta["reasoning_content"]
                    except Exception:
                        continue
        
        # contentが空ならreasoningを優先
        result = full_content.strip() or reasoning_content.strip()
        logger.info("LLM Complete (Streaming): Received %d chars", len(result))
        return result
        
    except Exception as e:
        logger.error("LLM stream request failed: %s", e)
        raise

def _try_repair_json(text: str) -> dict:
    """Robustly extracts and repairs JSON from LLM output."""
    import re
    text = text.strip()
    if not text: raise ValueError("Empty text")
    
    # 1. Look for the potential JSON block
    start_idx = text.find("{")
    if start_idx == -1: raise ValueError("No JSON object found")
    
    end_idx = text.rfind("}")
    if end_idx != -1 and end_idx > start_idx:
        candidate = text[start_idx:end_idx+1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Handle the specific LFM extra "]" case: ...intent.\"]}"
            cleaned = re.sub(r'\\?\"\](?=\s*\})', '"', candidate)
            try:
                return json.loads(cleaned)
            except:
                pass
    
    # 2. Additive repair for truncated JSON
    json_part = text[start_idx:]
    for suffix in ["}", "]}", "]} }", "\"}]}", "]} ]} }"]:
        try:
            return json.loads(json_part + suffix)
        except:
            continue
            
    # 3. Final desperate attempt: Extract via regex
    try:
        summary_match = re.search(r'\"summary\"\s*:\s*\"(.*?)\"', text, re.DOTALL)
        if summary_match:
            return {"summary": summary_match.group(1), "facts": []}
    except:
        pass
        
    raise ValueError("JSON repair failed")


# ---------------------------------------------------------------------------
# SSE streaming helper
# ---------------------------------------------------------------------------

async def _stream_llm(model_url: str, model_name: str, messages: list[dict]) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{model_url}/chat/completions",
            json={
                "model": model_name,
                "messages": messages,
                "max_tokens": 2048,
                "stream": True,
                "temperature": 0.7,
            },
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass


# ===========================================================================
# v1.3 ENDPOINTS (unchanged interface)
# ===========================================================================

# --- Health ---

@app.get("/api/health", response_model=HealthResponse, tags=["core"])
async def health():
    # Use cached list from router to avoid redundant LM Studio polling
    await model_router.refresh_available_models(force=False)
    
    lm_ok = len(model_router.available_model_ids) > 0
    active_models = model_router.available_model_ids
    schema = memory_manager.get_schema()
    return HealthResponse(
        status="ok",
        lm_studio_connected=lm_ok,
        active_models=active_models,
        memory_stats={
            "total_facts": len(schema.facts),
            "total_sessions": len(schema.sessions),
            "short_term_messages": len(schema.short_term.messages),
            "schema_version": schema.meta.schema_version,
        },
    )


# --- Session ---

@app.post("/api/session/new", response_model=NewSessionResponse, tags=["core"])
async def new_session():
    session_id = memory_manager.new_session()
    return NewSessionResponse(
        session_id=session_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# --- Refusal Detection (v2.0 NEW) ---

REFUSAL_KEYWORDS = [
    "i am sorry", "i'm sorry", "i cannot", "as an ai", "unfortunately",
    "ethical reasons", "安全上の理由", "提供できません", "申し訳ありません",
    "制限されています", "適切ではありません", "答えられません", "回答できません", "お答えできません", "できない"
]

def _is_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in REFUSAL_KEYWORDS)


# --- Chat (SSE streaming) ---

@app.post("/api/chat/stream", tags=["core"])
async def chat_stream(req: ChatRequest, background_tasks: BackgroundTasks):
    session_id = req.session_id

    # Ensure session exists
    if memory_manager.get_current_session_id() != session_id:
        memory_manager.new_session()

    # Determine initial model
    config = config_manager.get_config()
    route_result = None
    if req.override_model:
        model_cfg = model_router.get_model(req.override_model) or \
                    ModelConfig(name=req.override_model, url=f"{model_router.LM_STUDIO_BASE}/v1")
    else:
        route_result = await model_router.route(req.message)
        model_cfg = route_result.model

    # Build prompt once
    relevant_facts = memory_manager.search_facts(req.message, n_results=6)
    schema = memory_manager.get_schema()
    system_prompt = prompt_builder.build_system_prompt(schema, relevant_facts=relevant_facts)
    history = memory_manager.get_recent_messages(n=8)
    messages = prompt_builder.build_messages(system_prompt, history[:-0] if history else [], req.message)

    # Record user message once
    memory_manager.add_message("user", req.message)

    async def event_stream():
        nonlocal model_cfg
        
        # --- Attempt 1: Initial Model ---
        yield f"data: {json.dumps({'status': f'Preparing {model_cfg.name}...'})}\n\n"
        await model_router.ensure_model_loaded(model_cfg.name)

        full_response = ""
        buffer = ""
        buffer_limit = 250 # check first 250 chars for refusals
        fallback_triggered = False

        try:
            async for chunk in _stream_llm(model_cfg.url, model_cfg.name, messages):
                full_response += chunk
                
                if not fallback_triggered and len(full_response) < buffer_limit:
                    buffer += chunk
                    if _is_refusal(buffer):
                        if config.sub_model and model_cfg.name != config.sub_model:
                            logger.info("Refusal detected in %s, falling back to %s", model_cfg.name, config.sub_model)
                            fallback_triggered = True
                            break # Exists the loop for the first model
                
                yield f"data: {json.dumps({'delta': chunk})}\n\n"

        except Exception as e:
            logger.error("Initial stream error: %s", e)
            fallback_triggered = True

        if fallback_triggered and config.sub_model and model_cfg.name != config.sub_model:
            # --- Attempt 2: Fallback to Sub Model ---
            model_cfg = model_router.get_model(config.sub_model) or \
                        ModelConfig(name=config.sub_model, url=f"{model_router.LM_STUDIO_BASE}/v1")
            
            yield f"data: {json.dumps({'status': f'Censorship/Error detected. Switching to fallback model {model_cfg.name}...'})}\n\n"
            yield f"data: {json.dumps({'delta': '\\n\\n[Switching to sub-model due to restriction...]\\n\\n'})}\n\n"
            
            await model_router.ensure_model_loaded(model_cfg.name)
            
            next_response = ""
            try:
                async for chunk in _stream_llm(model_cfg.url, model_cfg.name, messages):
                    next_response += chunk
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
                full_response = next_response # Replace full_response for recording
            except Exception as e:
                logger.error("Fallback stream error: %s", e)
                yield f"data: {json.dumps({'error': f'All models failed: {str(e)}'})}\n\n"
                return

        # Mid-session consolidation check (async)
        if memory_manager.should_mid_consolidate():
            background_tasks.add_task(_background_consolidate, session_id, model_cfg.name, model_cfg.url)

        # Record assistant message
        memory_manager.add_message("assistant", full_response, model_used=model_cfg.name)
        trust_registry.record_output(model_cfg.name, bias_flagged=False)
        background_tasks.add_task(_background_bias_check, full_response, model_cfg.name)

        meta = {
            "model_used": model_cfg.name,
            "topic": route_result.topic_category if route_result else "manual",
            "session_id": session_id,
        }
        yield f"data: {json.dumps({'done': True, 'meta': meta})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Consolidate session ---

@app.post("/api/session/{session_id}/consolidate", tags=["core"])
async def consolidate_session(session_id: str):
    messages = memory_manager.get_recent_messages(n=50)
    if not messages:
        return {"status": "no_messages", "session_id": session_id}

    # Use consolidation model
    consol_model = model_router.get_consolidation_model()
    prompt = prompt_builder.build_consolidation_prompt(messages)

    logger.info("Starting consolidation using model: %s (URL: %s)", consol_model.name, consol_model.url)

    try:
        raw = await _llm_complete(
            consol_model.url,
            consol_model.name,
            [{"role": "user", "content": prompt}],
            max_tokens=1500,
        )
        logger.info("Consolidation LLM raw response: %s", raw)
        
        # Extract JSON block and parse via robust repairer
        try:
            parsed = _try_repair_json(raw)
        except Exception as e:
            logger.error("JSON extraction/repair failed: %s | Raw content: %s", e, raw)
            raise HTTPException(500, f"JSON parse error: {e}")
            
        logger.info("Parsed consolidation data: summary=%s, facts_count=%d", 
                    parsed.get("summary", ""), len(parsed.get("facts", [])))
    except Exception as e:
        logger.error("Consolidation LLM error (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Consolidation failed ({type(e).__name__}): {str(e)}"
        )

    result = await memory_manager.consolidate_session(
        session_id=session_id,
        summary=parsed.get("summary", ""),
        extracted_facts=parsed.get("facts", []),
        model_used=consol_model.name,
    )
    logger.info("Consolidation result: %s", result)
    return {"status": "ok", **result}


# --- Memory ---

@app.get("/api/memory", tags=["memory"])
async def get_memory():
    schema = memory_manager.get_schema()
    return schema.model_dump(by_alias=True)


@app.get("/api/memory/facts", tags=["memory"])
async def get_facts(source_type: str | None = None):
    facts = memory_manager.get_facts(source_type=source_type)
    return {"facts": [f.model_dump() for f in facts], "count": len(facts)}


@app.delete("/api/memory/facts/{fact_id}", tags=["memory"])
async def delete_fact(fact_id: str):
    ok = memory_manager.delete_fact(fact_id)
    if not ok:
        raise HTTPException(404, f"Fact not found: {fact_id}")
    return {"deleted": fact_id}


@app.post("/api/memory/search", tags=["memory"])
async def search_memory(body: dict):
    query = body.get("query", "")
    n = int(body.get("n_results", 5))
    facts = memory_manager.search_facts(query, n_results=n)
    return {"facts": [f.model_dump() for f in facts], "count": len(facts)}


@app.post("/api/memory/rebuild", tags=["memory"])
async def rebuild_memory():
    count = memory_manager.rebuild_chroma_index()
    return {"status": "ok", "indexed_facts": count}


# ===========================================================================
# v2.0 NEW ENDPOINTS
# ===========================================================================

# --- Model trust ---

@app.get("/api/models/trust", tags=["models"])
async def get_trust():
    return {"trust_registry": trust_registry.get_all()}


# --- Model routing ---

@app.post("/api/models/route", response_model=RouteQueryResponse, tags=["models"])
async def route_query(req: RouteQueryRequest):
    result = await model_router.route(req.query, context=req.context or "")
    return RouteQueryResponse(
        model_name=result.model.name,
        model_url=result.model.url,
        topic_category=result.topic_category,
        confidence=result.confidence,
        reason=result.reason,
    )


# --- Model list (all installed in LM Studio) ---

@app.get("/api/models/available", tags=["models"])
async def get_available_models():
    """
    Returns all models available in LM Studio.
    Tries /api/v0/models first (LM Studio 0.3.x, lists all installed models).
    Falls back to /v1/models (lists only currently loaded models).
    """
    lm_base = "http://127.0.0.1:1234"

    async with httpx.AsyncClient(timeout=5.0) as client:
        # --- Try newer LM Studio API (v0) first ---
        models_installed: list[dict] = []
        try:
            r = await client.get(f"{lm_base}/api/v0/models")
            if r.status_code == 200:
                data = r.json()
                raw = data if isinstance(data, list) else data.get("data", [])
                for m in raw:
                    model_id = m.get("id") or m.get("path") or str(m)
                    models_installed.append({
                        "id": model_id,
                        "loaded": m.get("state") == "loaded" or m.get("loaded", False),
                        "source": "v0",
                    })
        except Exception:
            pass

        # --- Fallback: /v1/models (loaded models only) ---
        try:
            r2 = await client.get(f"{lm_base}/v1/models")
            if r2.status_code == 200:
                loaded_ids = {m["id"] for m in r2.json().get("data", [])}
                if models_installed:
                    # Mark loaded state on v0 results
                    for m in models_installed:
                        if m["id"] in loaded_ids:
                            m["loaded"] = True
                else:
                    # Pure fallback — only loaded models are known
                    for mid in loaded_ids:
                        models_installed.append({"id": mid, "loaded": True, "source": "v1"})
        except Exception:
            pass

    return {
        "models": models_installed,
        "count": len(models_installed),
        "lm_studio_reachable": len(models_installed) > 0,
    }


# --- Model lifecycle ---

LM_STUDIO_BASE = "http://127.0.0.1:1234"

@app.post("/api/models/load", tags=["models"])
async def load_model(req: ModelLoadRequest):
    """
    Load a model in LM Studio using the robust router logic.
    """
    success = await model_router.ensure_model_loaded(req.model_name)
    return {
        "success": success,
        "model": req.model_name,
        "method": "router_ensure_loaded"
    }


@app.post("/api/models/unload", tags=["models"])
async def unload_model(body: dict):
    """
    Unload a model from LM Studio.
    Tries v0 API (DELETE /api/v0/models/{id}) first;
    falls back to setting keep_alive=0 via chat completion.
    """
    model_name = body.get("model_name", "")
    if not model_name:
        raise HTTPException(400, "model_name is required")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # --- Try LM Studio v0.3.x unload endpoint ---
        try:
            encoded = urllib.parse.quote(model_name, safe="")
            r = await client.delete(f"{LM_STUDIO_BASE}/api/v0/models/{encoded}")
            if r.status_code < 500:
                return {"success": True, "method": "v0_unload", "status_code": r.status_code, "model": model_name}
        except Exception as e:
            logger.warning("v0 unload attempt failed: %s", e)

        # --- Fallback: no-op (LM Studio manages lifecycle) ---
        logger.info("unload_model: %s — LM Studio manages lifecycle in v1 mode", model_name)
        return {
            "success": True,
            "method": "noop",
            "note": "LM Studio v1 API does not support explicit unload. Use LM Studio UI or upgrade to 0.3.x+",
            "model": model_name,
        }


# --- Config (v2.0 NEW) ---

@app.get("/api/config", response_model=PlamaConfig, tags=["config"])
async def get_config():
    return config_manager.get_config()


@app.post("/api/config", response_model=PlamaConfig, tags=["config"])
async def update_config(req: UpdateConfigRequest):
    return config_manager.update_config(
        main_model=req.main_model,
        sub_model=req.sub_model,
        bias_model=req.bias_model,
        consolidation_model=req.consolidation_model
    )


# --- Bias ---

@app.get("/api/bias/flags", tags=["bias"])
async def get_bias_flags(model: str | None = None, limit: int = 50):
    schema = memory_manager.get_schema()
    flagged = [f for f in schema.facts if f.bias_flag]
    if model:
        flagged = [f for f in flagged if f.model_origin == model]
    flagged = flagged[-limit:]
    return {"flags": [f.model_dump() for f in flagged], "count": len(flagged)}


@app.post("/api/bias/check", response_model=BiasCheckResponse, tags=["bias"])
async def check_bias(req: BiasCheckRequest):
    result = await bias_checker.check_async(req.text, model_origin=req.model_origin or "unknown")
    return BiasCheckResponse(**result)


# --- n8n pipeline ---

@app.post("/api/pipeline/n8n-ingest", tags=["pipeline"])
async def n8n_ingest(req: N8nIngestRequest):
    result = pipeline_ingest.ingest(req.source, req.language, req.documents)
    return result


@app.get("/api/pipeline/corpus/stats", tags=["pipeline"])
async def corpus_stats():
    return pipeline_ingest.get_corpus_stats()


@app.post("/api/pipeline/corpus/rebuild", tags=["pipeline"])
async def corpus_rebuild():
    return pipeline_ingest.rebuild_corpus_index()


# ===========================================================================
# Background tasks
# ===========================================================================

async def _background_consolidate(session_id: str, model_name: str, model_url: str):
    """Mid-session partial consolidation (v1.4)."""
    try:
        messages = memory_manager.get_recent_messages(n=20)
        prompt = prompt_builder.build_consolidation_prompt(messages)
        raw = await _llm_complete(model_url, model_name, [{"role": "user", "content": prompt}])
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(raw)
        await memory_manager.consolidate_session(
            session_id=session_id,
            summary=parsed.get("summary", ""),
            extracted_facts=parsed.get("facts", []),
            model_used=model_name,
        )
        logger.info("Mid-session consolidation completed for %s", session_id)
    except Exception as e:
        logger.error("Background consolidation error: %s", e)


async def _background_bias_check(text: str, model_name: str):
    """Run bias check and update TrustRegistry. v1.4: rule-based."""
    try:
        result = await bias_checker.check_async(text, model_origin=model_name)
        if result["bias_score"] > 0.3:
            trust_registry.record_output(model_name, bias_flagged=True)
            logger.warning("Bias detected from %s: score=%.2f flags=%s",
                           model_name, result["bias_score"], result["flags"])
    except Exception as e:
        logger.error("Background bias check error: %s", e)
