"""
PLAMA v2.0 - BiasChecker (LFM)
モデルの出力テキストを解析し、政治的バイアスや不適切な注入（CJKトークン等）を検出します。
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING, List, Dict, Any, Optional
from pydantic import BaseModel

if TYPE_CHECKING:
    from memory_manager import MemoryManager
    from model_router import ModelRouter
    from config_manager import ConfigManager

logger = logging.getLogger(__name__)

class BiasCheckResult(BaseModel):
    bias_score: float = 0.0
    flags: List[str] = []
    details: Dict[str, Any] = {}

class BiasChecker:
    """
    ChromaDBによる類似度判定とキーワードチェックを行うバイアス検知器。
    """
    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self._mm = memory_manager
        self.config_manager: Optional[ConfigManager] = None
        self.model_router: Optional[ModelRouter] = None

    async def check_async(self, text: str, model_origin: str = "unknown") -> BiasCheckResult:
        """
        非同期でバイアスチェックを実行します。
        ChromaDBの検索を含むため、メインスレッドをブロックしません。
        """
        flags = []
        details = {}
        
        # 1. ChromaDB コサイン類似度チェック (Propaganda Corpus)
        corpus_score = 0.0
        if self._mm:
            try:
                # MemoryManager経由で検索 (距離が小さいほど類似度が高い)
                results = self._mm.search_corpus(text, n_results=1)
                if results and "distances" in results and results["distances"]:
                    dist = results["distances"][0][0]
                    # コサイン類似度近似 (1.0 - 距離)
                    similarity = 1.0 - dist
                    if similarity > 0.8: # しきい値
                        flags.append("propaganda_similarity_high")
                        corpus_score = similarity
                        details["top_match_score"] = round(similarity, 4)
            except Exception as e:
                logger.warning(f"ChromaDB bias check failed: {e}")

        # 2. ルールベースチェック (CJKトークン注入など)
        if any(ord(c) > 0x3400 and ord(c) < 0x4DBF for c in text): # CJK Ext-A
            flags.append("unexpected_chinese_tokens")
            details["pattern"] = "cjk_ext_a"

        # スコア計算 (0.0 - 1.0)
        final_score = min(1.0, (corpus_score * 0.7) + (len(flags) * 0.2))

        return BiasCheckResult(
            bias_score=round(final_score, 4),
            flags=flags,
            details=details
        )

# Singleton instance
bias_checker = BiasChecker()
