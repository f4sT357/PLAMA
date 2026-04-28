"""
PLAMA v2.0 - Data Models (MemorySchema v2.0)
Pydantic models for memory schema, facts, sessions, trust registry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums / Literals
# ---------------------------------------------------------------------------

SourceType = Literal["explicit", "inference", "thinking", "consolidated", "unknown"]
FactCategory = Literal[
    "identity", "personality", "expertise", "preferences",
    "context", "goal", "relation", "event", "other"
]


# ---------------------------------------------------------------------------
# FactEntry
# ---------------------------------------------------------------------------

class FactEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"fact_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid4().hex[:6]}")
    content: str
    category: FactCategory = "other"
    confidence: float = Field(ge=0.0, le=0.9)   # hard cap 0.9 (v1.x design)
    source_type: SourceType = "unknown"
    expires_at: Optional[str] = None             # ISO8601 or null
    source_session: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = Field(default_factory=list)
    # --- v2.0 fields ---
    model_origin: str = "unknown"
    model_trust_score: float = Field(default=0.0, ge=0.0, le=1.0)
    bias_flag: bool = False
    bias_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def cap_confidence(cls, v: float) -> float:
        return min(v, 0.9)


# ---------------------------------------------------------------------------
# SessionEntry
# ---------------------------------------------------------------------------

class MessageEntry(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_used: Optional[str] = None   # v2.0: which model generated this


class ShortTermMemory(BaseModel):
    current_session_id: Optional[str] = None
    messages: list[MessageEntry] = Field(default_factory=list)
    max_messages: int = 50


class SessionEntry(BaseModel):
    id: str
    started_at: str
    ended_at: Optional[str] = None
    summary: Optional[str] = None
    message_count: int = 0
    models_used: list[str] = Field(default_factory=list)   # v2.0


# ---------------------------------------------------------------------------
# CoreProfile
# ---------------------------------------------------------------------------

class CoreProfile(BaseModel):
    identity: dict = Field(default_factory=dict)
    personality: list[str] = Field(default_factory=list)
    expertise: list[str] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# TrustRegistry (v2.0)
# ---------------------------------------------------------------------------

class ModelTrustEntry(BaseModel):
    total_outputs: int = 0
    bias_flags: int = 0
    trust_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    routing_preference: list[str] = Field(default_factory=list)
    avoid_topics: list[str] = Field(default_factory=list)

    def recalculate_trust(self) -> None:
        """Bayesian-style: penalise bias_flags / total_outputs."""
        if self.total_outputs == 0:
            self.trust_score = 1.0
            return
        flag_rate = self.bias_flags / self.total_outputs
        self.trust_score = round(max(0.0, min(0.9, 1.0 - flag_rate * 2)), 4)
        self.last_updated = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

class SchemaMeta(BaseModel):
    schema_version: str = "2.0"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_sessions: int = 0
    total_facts: int = 0


# ---------------------------------------------------------------------------
# Root MemorySchema
# ---------------------------------------------------------------------------

class MemorySchema(BaseModel):
    schema_: str = Field(default="MemorySchema v2.0", alias="$schema")
    meta: SchemaMeta = Field(default_factory=SchemaMeta)
    core_profile: CoreProfile = Field(default_factory=CoreProfile)
    facts: list[FactEntry] = Field(default_factory=list)
    sessions: list[SessionEntry] = Field(default_factory=list)
    short_term: ShortTermMemory = Field(default_factory=ShortTermMemory)
    model_trust_registry: dict[str, ModelTrustEntry] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def bump_updated(self) -> None:
        self.meta.last_updated = datetime.now(timezone.utc).isoformat()
        self.meta.total_facts = len(self.facts)
        self.meta.total_sessions = len(self.sessions)


# ---------------------------------------------------------------------------
# API Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str
    override_model: Optional[str] = None   # force a specific model (debug)


class NewSessionResponse(BaseModel):
    session_id: str
    created_at: str


class HealthResponse(BaseModel):
    status: str
    lm_studio_connected: bool
    active_models: list[str]
    memory_stats: dict


class RouteQueryRequest(BaseModel):
    query: str
    context: Optional[str] = None


class RouteQueryResponse(BaseModel):
    model_name: str
    model_url: str
    topic_category: str
    confidence: float
    reason: str


class ModelLoadRequest(BaseModel):
    model_name: str
    keep_alive: int = -1   # -1 = permanent


class PlamaConfig(BaseModel):
    main_model: str = ""
    sub_model: str = ""
    bias_model: str = ""
    consolidation_model: str = ""  # 記憶集約（Memory Keeper）
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UpdateConfigRequest(BaseModel):
    main_model: Optional[str] = None
    sub_model: Optional[str] = None
    bias_model: Optional[str] = None
    consolidation_model: Optional[str] = None


class BiasCheckRequest(BaseModel):
    text: str
    model_origin: Optional[str] = None


class BiasCheckResponse(BaseModel):
    bias_score: float
    flags: list[str]
    details: dict


class N8nIngestRequest(BaseModel):
    source: str
    language: str = "en"
    documents: list[dict]   # [{text, url, fetched_at}]
