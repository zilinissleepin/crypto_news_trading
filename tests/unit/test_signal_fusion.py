import asyncio
from datetime import datetime, timedelta, timezone

from apps.signal_fusion_service import SignalFusionService
from common_types import AppSettings


def test_signal_fusion_filters_low_confidence():
    settings = AppSettings(bus_backend="memory", min_signal_confidence=0.65)
    svc = SignalFusionService(settings)

    payload = {
        "event_id": "e1",
        "symbol": "BTCUSDT",
        "side": 1,
        "strength": 0.8,
        "confidence": 0.5,
        "horizon_min": 60,
        "ttl_sec": 3600,
        "rationale": "weak",
        "generated_at": datetime.now(timezone.utc),
    }
    out = asyncio.run(svc.handle(payload))
    assert out == []


def test_signal_fusion_blocks_conflict_signal():
    settings = AppSettings(bus_backend="memory", min_signal_confidence=0.65)
    svc = SignalFusionService(settings)

    now = datetime.now(timezone.utc)
    s1 = {
        "event_id": "e1",
        "symbol": "BTCUSDT",
        "side": 1,
        "strength": 0.7,
        "confidence": 0.8,
        "horizon_min": 60,
        "ttl_sec": 3600,
        "rationale": "good",
        "generated_at": now,
    }
    s2 = {
        "event_id": "e2",
        "symbol": "BTCUSDT",
        "side": -1,
        "strength": 0.65,
        "confidence": 0.82,
        "horizon_min": 60,
        "ttl_sec": 3600,
        "rationale": "bad",
        "generated_at": now + timedelta(minutes=5),
    }

    out1 = asyncio.run(svc.handle(s1))
    out2 = asyncio.run(svc.handle(s2))

    assert len(out1) == 1
    assert out2 == []
