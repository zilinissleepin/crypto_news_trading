from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    schema_version: str = "1.0"


class NewsEvent(BaseEvent):
    event_id: str
    source: str
    published_at: datetime
    title: str
    content: str
    lang: str = "en"
    url: str = ""
    dedup_hash: str


class EntityEvent(BaseEvent):
    event_id: str
    symbols: list[str]
    tags: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    relevance_score: float = Field(ge=0.0, le=1.0)
    title: str = ""
    content: str = ""


class SignalEvent(BaseEvent):
    event_id: str
    symbol: str
    side: Literal[-1, 0, 1]
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    horizon_min: int = Field(ge=1)
    ttl_sec: int = Field(ge=1)
    rationale: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrderIntent(BaseEvent):
    intent_id: str
    event_id: str
    symbol: str
    market: Literal["spot", "perp"]
    side: Literal[-1, 1]
    qty_usd: float = Field(gt=0.0)
    max_slippage_bps: int = Field(ge=1, le=200)
    reason: str


class RiskDecision(BaseEvent):
    intent_id: str
    allow: bool
    reason_code: str
    capped_qty_usd: float = Field(ge=0.0)


class ExecutionReport(BaseEvent):
    order_id: str
    intent_id: str
    symbol: str
    market: Literal["spot", "perp"]
    side: Literal[-1, 1]
    status: Literal["new", "partially_filled", "filled", "rejected", "canceled"]
    filled_qty: float = Field(ge=0.0)
    avg_price: float = Field(ge=0.0)
    fee: float = Field(ge=0.0)
    ts: datetime


class PnLSnapshot(BaseEvent):
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    account: str = "paper"
    unrealized: float = 0.0
    realized: float = 0.0
    exposure: float = 0.0
    drawdown: float = 0.0


class UniverseSignal(BaseEvent):
    signal: SignalEvent
    tradable: bool
    reason: str


STREAM_MODEL_MAP = {
    "news.raw": NewsEvent,
    "news.entity": EntityEvent,
    "signal.raw": SignalEvent,
    "signal.tradeable": SignalEvent,
    "signal.universe": SignalEvent,
    "order.intent": OrderIntent,
    "order.approved": OrderIntent,
    "order.rejected": RiskDecision,
    "execution.report": ExecutionReport,
    "pnl.snapshot": PnLSnapshot,
}


def validate_event(stream: str, payload: dict) -> BaseModel:
    model_cls = STREAM_MODEL_MAP.get(stream)
    if model_cls is None:
        raise ValueError(f"No model registered for stream: {stream}")
    return model_cls.model_validate(payload)


def is_stale(signal: SignalEvent, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    return (current - signal.generated_at).total_seconds() > signal.ttl_sec
