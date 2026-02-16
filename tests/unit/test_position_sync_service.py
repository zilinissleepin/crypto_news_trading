import asyncio

from apps.position_sync_service import PositionSyncService
from common_types import AppSettings
from common_types.bus import InMemoryEventBus
from feature_store import MemoryTradingStateStore


class FakeAdapter:
    def __init__(self, positions: list[dict]):
        self._positions = positions

    async def place_order(self, intent):
        del intent
        raise NotImplementedError

    async def cancel_order(self, order_id):
        del order_id
        return True

    async def fetch_positions(self) -> list[dict]:
        return list(self._positions)

    async def stream_execution_events(self):
        if False:
            yield {}


def test_position_sync_updates_state_snapshot_and_alerts_on_drift():
    settings = AppSettings(
        bus_backend="memory",
        execution_mode="live",
        account_equity_usd=100000,
        position_sync_drift_alert_pct=0.01,
    )
    bus = InMemoryEventBus()
    state = MemoryTradingStateStore()

    # Existing state has low exposure so drift will exceed threshold.
    asyncio.run(state.add_total_exposure(1000))

    adapter = FakeAdapter(
        [
            {"market": "spot", "symbol": "BTCUSDT", "qty": 0.1, "notional_usd": 6500},
            {"market": "perp", "symbol": "ETHUSDT", "qty": -1.2, "notional_usd": 3600},
        ]
    )
    svc = PositionSyncService(settings, adapter, state, bus)

    result = asyncio.run(svc.run_once())
    assert result["skipped"] is False
    assert round(asyncio.run(state.get_total_exposure()), 2) == 10100.00
    assert round(asyncio.run(state.get_market_exposure("spot")), 2) == 6500.00
    assert round(asyncio.run(state.get_market_exposure("perp")), 2) == 3600.00
    assert round(asyncio.run(state.get_side_exposure(1)), 2) == 6500.00
    assert round(asyncio.run(state.get_side_exposure(-1)), 2) == 3600.00

    alerts = asyncio.run(bus.read("risk.alert", "0-0"))
    assert len(alerts) == 1
    assert "reconciled" in alerts[0].data["message"]


def test_position_sync_skips_when_not_live_mode():
    settings = AppSettings(bus_backend="memory", execution_mode="paper")
    bus = InMemoryEventBus()
    state = MemoryTradingStateStore()
    adapter = FakeAdapter([{"market": "spot", "symbol": "BTCUSDT", "qty": 0.1, "notional_usd": 6500}])

    svc = PositionSyncService(settings, adapter, state, bus)
    result = asyncio.run(svc.run_once())
    assert result["skipped"] is True
    assert asyncio.run(state.get_total_exposure()) == 0.0
