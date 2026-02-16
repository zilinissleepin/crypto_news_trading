from common_types.models import OrderIntent
from exchange_adapters.binance import BinanceExchangeAdapter


def test_binance_signature_is_stable():
    adapter = BinanceExchangeAdapter("test_key", "test_secret", use_testnet=True, recv_window_ms=5000)
    query = "symbol=BTCUSDT&timestamp=1&recvWindow=5000"
    signature = adapter._signature(query)
    assert signature == "93ca47104e4c2ee71fd76bbff75015d3a5f8868433f9045c387210dba928307e"


def test_binance_sign_params_appends_required_fields():
    adapter = BinanceExchangeAdapter("test_key", "test_secret", use_testnet=True, recv_window_ms=5000)
    signed = adapter._sign_params({"symbol": "BTCUSDT"})
    assert signed["symbol"] == "BTCUSDT"
    assert "timestamp" in signed
    assert "recvWindow" in signed
    assert "signature" in signed


def test_binance_order_id_shape_for_spot_report(monkeypatch):
    adapter = BinanceExchangeAdapter("test_key", "test_secret", use_testnet=True)

    async def fake_request(**kwargs):
        del kwargs
        return {
            "orderId": 123,
            "executedQty": "0.1",
            "fills": [{"price": "65000", "qty": "0.1", "commission": "0.01"}],
            "status": "FILLED",
        }

    adapter._request = fake_request  # type: ignore
    intent = OrderIntent(
        intent_id="intent-1",
        event_id="evt-1",
        symbol="BTCUSDT",
        market="spot",
        side=1,
        qty_usd=100,
        max_slippage_bps=20,
        reason="test",
    )

    import asyncio

    report = asyncio.run(adapter.place_order(intent))
    assert report.order_id == "spot:BTCUSDT:123"
    assert report.status == "filled"
