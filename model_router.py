"""
PLAMA v1.4 - ModelRouter
Keyword-based query routing to appropriate LLM models.
v2.0 will add LFM-based classification; v1.4 uses rule-based matching.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import httpx
import urllib.parse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    name: str           # display name / model identifier for LM Studio
    url: str            # inference endpoint
    topic_tags: list[str] = field(default_factory=list)  # routing preference topics
    avoid_tags: list[str] = field(default_factory=list)  # topics to avoid
    priority: int = 0   # higher = preferred when multiple match


# Default model registry - override via env / config
DEFAULT_MODELS: list[ModelConfig] = [
    ModelConfig(
        name="mistral-7b",
        url="http://127.0.0.1:1234/v1",
        topic_tags=["geopolitics", "politics", "diplomacy", "history", "international"],
        avoid_tags=[],
        priority=10,
    ),
    ModelConfig(
        name="qwen3.5-4b",
        url="http://127.0.0.1:1234/v1",
        topic_tags=["japanese", "general", "daily", "conversation", "summary"],
        avoid_tags=["geopolitics", "politics", "diplomacy"],
        priority=5,
    ),
    ModelConfig(
        name="qwen3.5-9b",
        url="http://127.0.0.1:1234/v1",
        topic_tags=["code", "technical", "programming", "architecture", "analysis"],
        avoid_tags=["geopolitics", "politics"],
        priority=7,
    ),
]

# Consolidation model (fixed, quality-stable)
CONSOLIDATION_MODEL = "qwen3.5-9b"
LM_STUDIO_BASE = "http://127.0.0.1:1234"
CONSOLIDATION_URL = f"{LM_STUDIO_BASE}/v1"


# ---------------------------------------------------------------------------
# Topic keyword maps
# ---------------------------------------------------------------------------

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "geopolitics": [
        "china", "russia", "taiwan", "ukraine", "nato", "geopolitics",
        "中国", "ロシア", "台湾", "地政学", "外交", "制裁", "安全保障",
        "xinjiang", "tibet", "hong kong", "sanctions", "territorial",
        "sovereignty", "propaganda", "espionage", "military", "war",
        "conflict", "uighur", "ウイグル", "南シナ海", "尖閣",
    ],
    "politics": [
        "election", "政治", "government", "policy", "democrat", "republican",
        "parliament", "constitution", "ideology", "conservative", "liberal",
        "選挙", "政策", "政府", "自民党", "民主党", "国会", "憲法",
    ],
    "history": [
        "history", "war", "wwii", "cold war", "revolution", "empire",
        "歴史", "戦争", "冷戦", "革命", "帝国", "植民地", "占領",
        "holocaust", "genocide", "atrocity", "second world war",
    ],
    "code": [
        "code", "python", "javascript", "typescript", "rust", "function",
        "bug", "debug", "algorithm", "api", "database", "sql", "git",
        "コード", "実装", "バグ", "関数", "クラス", "テスト", "リファクタ",
        "dockerfile", "kubernetes", "fastapi", "react", "next.js",
    ],
    "technical": [
        "architecture", "system design", "microservice", "llm", "transformer",
        "embedding", "vector", "chromadb", "neural", "model", "inference",
        "アーキテクチャ", "設計", "システム", "ベクトル", "推論", "量子化",
        "quantization", "gguf", "lora", "fine-tuning",
    ],
    "japanese": [
        "日本語", "敬語", "です", "ます", "ください", "てください",
        "japanese", "nihongo",
    ],
    "general": [],  # fallback
}


# ---------------------------------------------------------------------------
# Routing result
# ---------------------------------------------------------------------------

@dataclass
class RoutingResult:
    model: ModelConfig
    topic_category: str
    confidence: float
    reason: str


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class ModelRouter:
    """
    v1.4: Keyword-based routing.
    v2.0 TODO: add LFM-based semantic classification as secondary pass.
    """

    def __init__(
        self,
        models: list[ModelConfig] | None = None,
        default_model_name: str = "qwen3.5-4b",
        config_manager: "ConfigManager" | None = None,
    ):
        self.models = models or list(DEFAULT_MODELS)
        self._model_map: dict[str, ModelConfig] = {m.name: m for m in self.models}
        self.default_model_name = default_model_name
        self.config_manager = config_manager
        self.available_model_ids: list[str] = []
        self._last_refresh = 0.0
        self._cache_ttl = 60.0  # 60秒間キャッシュ

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(self, query: str, context: str = "") -> RoutingResult:
        """
        Determine the best model for a given query.
        Returns RoutingResult with selected ModelConfig.
        """
        config = self.config_manager.get_config() if self.config_manager else None
        
        # High-level override: if the user set a specific main/sub model, use those as priority
        text = (query + " " + context).lower()
        topic_scores = self._score_topics(text)

        # Pick the dominant topic (highest score)
        dominant_topic, topic_score = max(topic_scores.items(), key=lambda x: x[1])

        if topic_score == 0:
            dominant_topic = "general"

        # Find best model for this topic
        model, reason = await self._select_model_dynamic(dominant_topic, topic_score, config)
        confidence = min(0.95, topic_score / 3.0) if topic_score > 0 else 0.3

        logger.info(
            "ModelRouter: query=%r topic=%s score=%d model=%s",
            query[:60], dominant_topic, topic_score, model.name,
        )

        return RoutingResult(
            model=model,
            topic_category=dominant_topic,
            confidence=round(confidence, 3),
            reason=reason,
        )

    def get_consolidation_model(self) -> ModelConfig:
        config = self.config_manager.get_config() if self.config_manager else None
        if config and config.consolidation_model:
            return ModelConfig(name=config.consolidation_model, url=CONSOLIDATION_URL)
        
        if CONSOLIDATION_MODEL in self._model_map:
            return self._model_map[CONSOLIDATION_MODEL]
        return self.models[0]

    def get_model(self, name: str) -> ModelConfig | None:
        return self._model_map.get(name)

    def list_models(self) -> list[ModelConfig]:
        """List current static + dynamic models based on config."""
        return list(self.models)

    # ------------------------------------------------------------------
    # LM Studio Management (v2.0 NEW)
    # ------------------------------------------------------------------

    async def get_loaded_model_ids(self) -> List[str]:
        """Fetch current loaded model IDs from LM Studio /v1/models."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{LM_STUDIO_BASE}/v1/models")
                if r.status_code == 200:
                    data = r.json()
                    return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning("Failed to fetch loaded models: %s", e)
        return []

    async def unload_all_models(self):
        """Unload all currently loaded models from LM Studio."""
        loaded_ids = await self.get_loaded_model_ids()
        if not loaded_ids:
            return

        logger.info("Unloading all models to free VRAM: %s", loaded_ids)
        async with httpx.AsyncClient(timeout=30.0) as client:
            for mid in loaded_ids:
                try:
                    encoded = urllib.parse.quote(mid, safe="")
                    # Try v0 DELETE (unload)
                    r = await client.delete(f"{LM_STUDIO_BASE}/api/v0/models/{encoded}")
                    logger.info("Unloaded %s (status %d)", mid, r.status_code)
                except Exception as e:
                    logger.warning("Failed to unload %s: %s", mid, e)

    async def ensure_model_loaded(self, model_id: str, gpu: str = "max", force_unload: bool = True) -> bool:
        """
        Ensure the specified model is loaded. 
        gpu: "max" (GPU) or "off" (CPU)
        force_unload: If True, unloads all other models first to free VRAM.
        """
        loaded_ids = await self.get_loaded_model_ids()
        if model_id in loaded_ids:
            logger.info("Model already loaded: %s", model_id)
            return True

        if force_unload:
            # Unload others first (conservative memory management)
            await self.unload_all_models()

        logger.info("Starting load process for model: %s (gpu=%s)", model_id, gpu)
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try Variant 1: POST /api/v0/models/{id}/load
            try:
                encoded = urllib.parse.quote(model_id, safe="")
                r = await client.post(f"{LM_STUDIO_BASE}/api/v0/models/{encoded}/load", json={"ttl": -1, "gpu": gpu})
                logger.info("Variant 1 status: %d", r.status_code)
            except Exception: pass

            # Try Variant 2: POST /api/v0/model/load
            try:
                r = await client.post(f"{LM_STUDIO_BASE}/api/v0/model/load", json={"modelId": model_id, "ttl": -1, "gpu": gpu})
                logger.info("Variant 2 status: %d", r.status_code)
            except Exception: pass

            # Try Variant 3: auto-load trigger
            try:
                # Note: v1 API might not support 'gpu' param directly in chat/completions, 
                # but we send it anyway as many backends ignore unknown fields.
                await client.post(f"{LM_STUDIO_BASE}/v1/chat/completions", json={"model": model_id, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1, "gpu": gpu}, timeout=5.0)
            except Exception: pass

        # Polling: Wait for model to appear in /v1/models
        logger.info("Polling LM Studio for %s...", model_id)
        for i in range(40):
            await asyncio.sleep(1.5)
            if model_id in await self.get_loaded_model_ids():
                logger.info("Model %s is now LOADED.", model_id)
                return True
        logger.error("Model load timed out: %s", model_id)
        return False



    async def list_loaded_models(self) -> list[str]:
        """Query LM Studio for currently loaded models."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{LM_STUDIO_BASE}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning("list_loaded_models failed: %s", e)
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_topics(self, text: str) -> dict[str, int]:
        scores: dict[str, int] = {topic: 0 for topic in TOPIC_KEYWORDS}
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                # whole-word match for ASCII, substring for CJK
                if re.search(r'\b' + re.escape(kw) + r'\b', text) or \
                   (any(ord(c) > 0x2E7F for c in kw) and kw in text):
                    scores[topic] += 1
        return scores

    async def refresh_available_models(self, force: bool = False):
        """Query LM Studio for all available/installed model IDs."""
        import time
        now = time.time()
        if not force and (now - self._last_refresh < self._cache_ttl) and self.available_model_ids:
            return
        
        self._last_refresh = now
        self.available_model_ids = await self.list_loaded_models()
        # Also try to get all known/installed (v0 API) if available
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{LM_STUDIO_BASE}/api/v0/models")
                if r.status_code == 200:
                    data = r.json()
                    ids = [m.get("id") or m.get("path") for m in data if isinstance(data, list)]
                    if not ids and isinstance(data, dict):
                        ids = [m.get("id") or m.get("path") for m in data.get("data", [])]
                    for i in ids:
                        if i and i not in self.available_model_ids:
                            self.available_model_ids.append(i)
        except Exception:
            pass

    async def _select_model_dynamic(self, topic: str, score: int, config: "PlamaConfig" | None) -> tuple[ModelConfig, str]:
        # 1. Check user-defined configuration roles
        preferred_id = ""
        if topic in ["code", "technical", "geopolitics"] and config and config.sub_model:
            preferred_id = config.sub_model
        elif config and config.main_model:
            preferred_id = config.main_model

        if preferred_id:
            # If we have a preferred ID, always use it (bypassing strict availability check sync issues)
            return ModelConfig(name=preferred_id, url=f"{LM_STUDIO_BASE}/v1"), f"User set '{preferred_id}' as preferred for role/topic"

        # 2. Fallback to hardcoded mapping if available
        candidates = [
            m for m in self.models
            if (topic in m.topic_tags or topic == "general")
            and topic not in m.avoid_tags
            and (m.name in self.available_model_ids or not self.available_model_ids)
        ]

        if candidates:
            best = max(candidates, key=lambda m: m.priority)
            return best, f"Topic='{topic}' matched hardcoded '{best.name}'"

        # 3. Ultimate Fallback: just use anything available in LM Studio
        if self.available_model_ids:
            # Prefer currently loaded if any (first in list from /v1/models usually)
            fallback_id = self.available_model_ids[0]
            return ModelConfig(name=fallback_id, url=f"{LM_STUDIO_BASE}/v1"), f"Fallback to first available LM Studio model: {fallback_id}"

        # 4. Total fallback (bootstrapping / LM Studio offline)
        return self.models[0], "Total fallback (no models reachable)"

    def _select_model(self, topic: str, score: int) -> tuple[ModelConfig, str]:
        # Legacy method (keeps compatibility if called synchronously)
        candidates = [
            m for m in self.models
            if (topic in m.topic_tags or topic == "general")
            and topic not in m.avoid_tags
        ]
        if not candidates:
            return self.models[0], "Legacy fallback"
        best = max(candidates, key=lambda m: m.priority)
        return best, "Legacy match"


# ---------------------------------------------------------------------------
# Module-level singleton (imported by main.py)
# ---------------------------------------------------------------------------

router = ModelRouter()
