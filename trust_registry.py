"""
PLAMA v1.4 - TrustRegistry
Thin CRUD layer over MemorySchema.model_trust_registry.
Full scoring implemented in v1.5.
"""
from __future__ import annotations

from models import ModelTrustEntry


class TrustRegistry:
    """
    Wraps MemoryManager's trust_registry operations.
    Imported by main.py for the /api/models/trust endpoint.
    """

    def __init__(self, memory_manager):
        self._mm = memory_manager

    def get_all(self) -> dict[str, dict]:
        return {k: v.model_dump() for k, v in self._mm.get_trust_registry().items()}

    def get(self, model_name: str) -> dict | None:
        reg = self._mm.get_trust_registry()
        entry = reg.get(model_name)
        return entry.model_dump() if entry else None

    def record_output(self, model_name: str, bias_flagged: bool = False) -> None:
        self._mm.record_model_output(model_name, bias_flagged)

    def initialize_model(self, model_name: str, routing_preference: list[str], avoid_topics: list[str]) -> None:
        """Register a new model in the trust registry."""
        schema = self._mm.get_schema()
        if model_name not in schema.model_trust_registry:
            schema.model_trust_registry[model_name] = ModelTrustEntry(
                routing_preference=routing_preference,
                avoid_topics=avoid_topics,
            )
            self._mm._save_schema()
