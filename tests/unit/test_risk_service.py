import asyncio

from apps.risk_service import RiskService
from common_types import AppSettings
from feature_store import MemoryTradingStateStore


def test_risk_caps_exposure_by_symbol_limit():
    settings = AppSettings(
        bus_backend="memory",
        account_equity_usd=100000,
        max_symbol_exposure_pct=0.05,
        max_total_exposure_pct=0.2,
    )
    state = MemoryTradingStateStore()
    svc = RiskService(settings, state)

    payload = {
        "intent_id": "i1",
        "event_id": "e1",
        "symbol": "BTCUSDT",
        "market": "spot",
        "side": 1,
        "qty_usd": 7000,
        "max_slippage_bps": 20,
        "reason": "test",
    }

    out = asyncio.run(svc.handle_order_intent(payload))
    assert len(out) == 1
    stream, approved = out[0]
    assert stream == "order.approved"
    assert approved["qty_usd"] == 5000


def test_risk_rejects_when_market_limit_is_exhausted():
    settings = AppSettings(
        bus_backend="memory",
        account_equity_usd=100000,
        max_symbol_exposure_pct=0.5,
        max_total_exposure_pct=0.5,
        max_spot_exposure_pct=0.03,
        max_long_exposure_pct=0.5,
    )
    state = MemoryTradingStateStore()
    svc = RiskService(settings, state)

    first = {
        "intent_id": "spot-1",
        "event_id": "e1",
        "symbol": "ETHUSDT",
        "market": "spot",
        "side": 1,
        "qty_usd": 3000,
        "max_slippage_bps": 20,
        "reason": "fill market limit",
    }
    second = {
        "intent_id": "spot-2",
        "event_id": "e2",
        "symbol": "BTCUSDT",
        "market": "spot",
        "side": 1,
        "qty_usd": 100,
        "max_slippage_bps": 20,
        "reason": "should reject",
    }

    out1 = asyncio.run(svc.handle_order_intent(first))
    out2 = asyncio.run(svc.handle_order_intent(second))

    assert out1[0][0] == "order.approved"
    assert out2[0][0] == "order.rejected"
    assert out2[0][1]["reason_code"] == "MARKET_EXPOSURE_LIMIT"


def test_risk_rejects_when_short_side_limit_is_exhausted():
    settings = AppSettings(
        bus_backend="memory",
        account_equity_usd=100000,
        max_symbol_exposure_pct=0.5,
        max_total_exposure_pct=0.5,
        max_perp_exposure_pct=0.5,
        max_short_exposure_pct=0.02,
    )
    state = MemoryTradingStateStore()
    svc = RiskService(settings, state)

    first = {
        "intent_id": "short-1",
        "event_id": "e1",
        "symbol": "BTCUSDT",
        "market": "perp",
        "side": -1,
        "qty_usd": 2000,
        "max_slippage_bps": 20,
        "reason": "fill short limit",
    }
    second = {
        "intent_id": "short-2",
        "event_id": "e2",
        "symbol": "ETHUSDT",
        "market": "perp",
        "side": -1,
        "qty_usd": 100,
        "max_slippage_bps": 20,
        "reason": "should reject",
    }

    out1 = asyncio.run(svc.handle_order_intent(first))
    out2 = asyncio.run(svc.handle_order_intent(second))

    assert out1[0][0] == "order.approved"
    assert out2[0][0] == "order.rejected"
    assert out2[0][1]["reason_code"] == "SIDE_EXPOSURE_LIMIT"
