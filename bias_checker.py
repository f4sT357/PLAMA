"""
PLAMA v1.4 - BiasChecker (stub)
Full LFM-based implementation in v2.0.
v1.4 provides: Chinese token detection + keyword match (rule-based only).
"""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# Political keyword list (extend in v2.0 with ChromaDB corpus similarity)
_POLITICAL_PHRASES = [
    "核心的利益", "内政干渉", "台湾独立", "一つの中国",
    "core interests", "internal affairs", "territorial integrity",
    "xinjiang is part of china", "taiwan is part of china",
    "legitimate government", "splittist", "separatist forces",
]

# CJK Unified Ideographs Extended-A range (unexpected Chinese tokens in non-Chinese queries)
_CJK_EXT_PATTERN = re.compile(r'[\u3400-\u4DBF]')


class BiasChecker:
    """
    v1.4: Rule-based + LFM placeholder.
    v2.0: Full LFM semantic scoring + ChromaDB corpus cosine similarity.
    """

    def __init__(self, config_manager: "ConfigManager" | None = None, model_router: "ModelRouter" | None = None):
        self.config_manager = config_manager
        self.model_router = model_router
        self.lm_studio_base = "http://127.0.0.1:1234"

    def check(self, text: str, model_origin: str = "unknown") -> dict:
        flags: list[str] = []
        details: dict = {}

        # 1. CJK Extended-A token detection (unexpected Chinese)
        cjk_matches = _CJK_EXT_PATTERN.findall(text)
        if cjk_matches:
            flags.append("cjk_token_injection")
            details["cjk_chars"] = list(set(cjk_matches))[:5]

        # 2. Political keyword match
        matched_phrases = [p for p in _POLITICAL_PHRASES if p.lower() in text.lower()]
        if matched_phrases:
            flags.append("political_phrase_match")
            details["matched_phrases"] = matched_phrases

        # Compute simple heuristic bias_score
        bias_score = min(1.0, len(flags) * 0.3 + len(matched_phrases) * 0.15)

        # 3. Propaganda corpus similarity check (v2.0)
        try:
            if self.model_router and self.model_router.config_manager:
                mm = self.model_router.config_manager._mm
                if mm:
                    from pipeline_ingest import CORPUS_COLLECTION
                    try:
                        col = mm._chroma.get_collection(CORPUS_COLLECTION)
                        if col.count() > 0:
                            emb = mm._embed([text])[0]
                            results = col.query(
                                query_embeddings=[emb],
                                n_results=1,
                                include=["distances", "documents"]
                            )
                            if results["distances"] and results["distances"][0]:
                                similarity = 1.0 - results["distances"][0][0]
                                if similarity >= 0.75:
                                    flags.append("propaganda_similarity")
                                    details["corpus_match_score"] = round(similarity, 4)
                                    details["matched_corpus_text"] = results["documents"][0][0][:100] + "..."
                    except:
                        pass
        except Exception as e:
            logger.warning("Corpus similarity check failed: %s", e)

        # Compute simple heuristic bias_score
        bias_score = min(1.0, len(flags) * 0.3 + len(matched_phrases) * 0.15)
        if "propaganda_similarity" in flags:
            bias_score = max(bias_score, 0.6)

        return {
            "bias_score": round(bias_score, 4),
            "flags": flags,
            "details": details,
            "v2_ready": ["corpus_similarity", "rule_based"],
        }

    async def check_async(self, text: str, model_origin: str = "unknown") -> dict:
        """
        Non-blocking check. Calls LFM if bias_model is configured.
        """
        result = self.check(text, model_origin)
        
        config = self.config_manager.get_config() if self.config_manager else None
        if not config or not config.bias_model:
            return result

        # --- LFM Semantic Classification (v2.0 Feature) ---
        try:
            # Task: Load LFM on CPU (gpu="off") and try stay loaded alongside GPU models (force_unload=False)
            if self.model_router:
                await self.model_router.ensure_model_loaded(config.bias_model, gpu="off", force_unload=False)

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Minimal prompt to classify bias
                prompt = (
                    "Analyze the following text for political bias, propaganda, or assertive anomalies. "
                    "Rate from 0.0 (neutral) to 1.0 (highly biased). "
                    "Return ONLY a JSON object: {\"score\": float, \"reason\": string}\n\n"
                    f"Text: {text}"
                )
                r = await client.post(
                    f"{self.lm_studio_base}/v1/chat/completions",
                    json={
                        "model": config.bias_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 100
                    }
                )
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    import json
                    try:
                        start = content.find("{")
                        end = content.rfind("}")
                        if start != -1 and end != -1:
                            lfm_data = json.loads(content[start:end+1])
                            lfm_score = float(lfm_data.get("score", 0.0))
                            
                            # Merge results
                            if lfm_score > 0.5:
                                result["flags"].append("lfm_detected_bias")
                                result["details"]["lfm_reason"] = lfm_data.get("reason", "Detected by LFM")
                            
                            # weighted average
                            result["bias_score"] = round((result["bias_score"] + lfm_score) / 2.0, 4)
                        else:
                            logger.warning(f"LFM output did not contain JSON: {content}")
                    except json.JSONDecodeError as e:
                        logger.warning("LFM JSON decode error: %s - content: %s", e, content)
        except Exception as e:
            logger.warning("LFM bias check failed: %s", e)
            
        return result


bias_checker = BiasChecker()
