"""
PLAMA v2.0 - TrustRegistry
MemorySchema.model_trust_registryに対するCRUD操作を提供するレイヤーです。
書き込みはMemoryManagerを通じて永続化されます。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from models import ModelTrustEntry

if TYPE_CHECKING:
    from memory_manager import MemoryManager

class TrustRegistry:
    """
    MemoryManagerの信頼レジストリ操作をラップします。
    複雑なスコアリングロジックは含まず、データの取得と更新に専念します。
    """

    def __init__(self, memory_manager: MemoryManager):
        self._mm = memory_manager

    def get_all_entries(self) -> dict[str, ModelTrustEntry]:
        """登録されている全モデルの信頼情報を取得します。"""
        return self._mm.get_trust_registry()

    def get_entry(self, model_name: str) -> Optional[ModelTrustEntry]:
        """特定のモデルの信頼情報を取得します。"""
        registry = self._mm.get_trust_registry()
        return registry.get(model_name)

    def record_model_result(self, model_name: str, is_biased: bool = False) -> None:
        """
        モデルの出力結果を記録します。
        MemoryManager側で統計の更新と保存が行われます。
        """
        self._mm.record_model_output(model_name, bias_flagged=is_biased)

    def initialize_model(
        self, 
        model_name: str, 
        routing_preference: list[str] = None, 
        avoid_topics: list[str] = None
    ) -> None:
        """
        新しいモデルをレジストリに初期登録します。
        既に存在する場合はスキップします。
        """
        schema = self._mm.get_schema()
        if model_name not in schema.model_trust_registry:
            schema.model_trust_registry[model_name] = ModelTrustEntry(
                routing_preference=routing_preference or [],
                avoid_topics=avoid_topics or [],
            )
            # 内部メソッドを直接呼び出すか、MemoryManager側にセーブ用公開メソッドがあることを想定
            self._mm._save_schema()

    def update_model_preferences(
        self, 
        model_name: str, 
        routing_preference: list[str], 
        avoid_topics: list[str]
    ) -> bool:
        """特定のモデルのルーティング設定や回避トピックを更新します。"""
        schema = self._mm.get_schema()
        if model_name in schema.model_trust_registry:
            entry = schema.model_trust_registry[model_name]
            entry.routing_preference = routing_preference
            entry.avoid_topics = avoid_topics
            self._mm._save_schema()
            return True
        return False
