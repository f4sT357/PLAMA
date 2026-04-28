"""
PLAMA v2.0 - ModelRouter
クエリのキーワードに基づき、最適なLLMモデルを選択します。
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from config_manager import ConfigManager

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    name: str
    url: str
    topic_tags: list[str] = field(default_factory=list)
    avoid_tags: list[str] = field(default_factory=list)
    priority: int = 0

@dataclass
class RoutingResult:
    model_name: str
    model_url: str
    topic_category: str
    confidence: float
    reason: str

# ---------------------------------------------------------------------------
# Topic Definition
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS = {
    "geopolitics": ["china", "russia", "war", "politics", "地政学", "外交", "軍事"],
    "technical": ["code", "python", "programming", "architecture", "実装", "バグ"],
    "creative": ["story", "novel", "poem", "creative", "物語", "創作", "詩"],
    "general": [] # フォールバック
}

class ModelRouter:
    """
    キーワードマッチングによるLLMルーティング。
    """
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager
        self.lm_studio_base = "http://127.0.0.1:1234/v1"
        self.available_model_ids: List[str] = []

    async def route(self, query: str) -> RoutingResult:
        """クエリを解析し、最適なモデルを決定します。"""
        text = query.lower()
        
        # 1. キーワードスコアリング
        scores = {topic: 0 for topic in TOPIC_KEYWORDS}
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[topic] += 1
        
        dominant_topic, score = max(scores.items(), key=lambda x: x[1])
        if score == 0:
            dominant_topic = "general"

        # 2. 設定に基づいたモデル選択
        config = self.config_manager.get_config() if self.config_manager else None
        
        # 基本的には main_model を使用し、特定のトピックでは sub_model を検討
        selected_model = config.main_model if config and config.main_model else "default-model"
        
        if dominant_topic in ["technical", "geopolitics"] and config and config.sub_model:
            selected_model = config.sub_model
            reason = f"Topic '{dominant_topic}' matches sub_model preference."
        else:
            reason = f"Defaulting to main_model for topic '{dominant_topic}'."

        confidence = 0.5 + (min(score, 5) / 10.0)

        return RoutingResult(
            model_name=selected_model,
            model_url=self.lm_studio_base,
            topic_category=dominant_topic,
            confidence=confidence,
            reason=reason
        )

    def get_consolidation_model(self) -> str:
        """記憶集約用のモデル名を取得します。"""
        config = self.config_manager.get_config() if self.config_manager else None
        return config.consolidation_model if config and config.consolidation_model else "qwen-9b"

    async def refresh_available_models(self, force: bool = False):
        """利用可能なモデルリストを更新します（スタブ）。"""
        # 実際のLM Studio API呼び出しはmain.py等で行われるため、ここではリストの保持に留める
        pass

    async def ensure_model_loaded(self, model_id: str) -> bool:
        """モデルがロードされているか確認し、必要ならロードします（スタブ）。"""
        return True

    def list_models(self) -> List[ModelConfig]:
        """静的に定義されたモデルリストを返します。"""
        return []

# Singleton instance
router = ModelRouter()
