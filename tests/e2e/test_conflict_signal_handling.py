import asyncio
from datetime import datetime, timedelta, timezone

from apps.signal_fusion_service import SignalFusionService
from common_types import AppSettings


def test_conflicting_signals_do_not_double_trigger():
    settings = AppSettings(bus_backend="memory", min_signal_confidence=0.65)
    svc = SignalFusionService(settings)

    base = datetime.now(timezone.utc)
    long_signal = {
        "event_id": "event-long",
        "symbol": "ETHUSDT",
        "side": 1,
        "strength": 0.72,
        "confidence": 0.8,
        "horizon_min": 120,
        "ttl_sec": 3600,
        "rationale": "positive catalyst",
        "generated_at": base,
    }
    short_signal = {
        "event_id": "event-short",
        "symbol": "ETHUSDT",
        "side": -1,
        "strength": 0.70,
        "confidence": 0.79,
        "horizon_min": 120,
        "ttl_sec": 3600,
        "rationale": "negative catalyst",
        "generated_at": base + timedelta(minutes=10),
    }

    out_long = asyncio.run(svc.handle(long_signal))
    out_short = asyncio.run(svc.handle(short_signal))

    assert len(out_long) == 1
    assert out_short == []
