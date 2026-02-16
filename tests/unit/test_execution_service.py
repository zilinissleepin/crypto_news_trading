import asyncio
from datetime import datetime, timezone

from apps.execution_service import ExecutionService
from common_types.models import ExecutionReport
from exchange_adapters import SimulatedExchangeAdapter


def test_execution_service_deduplicates_intent():
    service = ExecutionService(SimulatedExchangeAdapter())
    payload = {
        "intent_id": "intent-1",
        "event_id": "e1",
        "symbol": "BTCUSDT",
        "market": "spot",
        "side": 1,
        "qty_usd": 100,
        "max_slippage_bps": 20,
        "reason": "test",
    }

    first = asyncio.run(service.handle(payload))
    second = asyncio.run(service.handle(payload))

    assert len(first) == 1
    assert second == []


def test_execution_service_deduplicates_adapter_events():
    service = ExecutionService(SimulatedExchangeAdapter())
    event = ExecutionReport(
        order_id="spot:BTCUSDT:1",
        intent_id="intent-1",
        symbol="BTCUSDT",
        market="spot",
        side=1,
        status="filled",
        filled_qty=0.1,
        avg_price=65000,
        fee=0.0,
        ts=datetime.now(timezone.utc),
    ).model_dump(mode="json")

    one = service.normalize_adapter_event(event)
    two = service.normalize_adapter_event(event)

    assert one is not None
    assert two is None
