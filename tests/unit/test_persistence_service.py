from datetime import datetime, timezone

from apps.persistence_service import merge_execution_state
from common_types.models import ExecutionReport


def _report(status: str, filled_qty: float, avg_price: float, ts_sec: int) -> ExecutionReport:
    return ExecutionReport(
        order_id="spot:BTCUSDT:1",
        intent_id="intent-1",
        symbol="BTCUSDT",
        market="spot",
        side=1,
        status=status,
        filled_qty=filled_qty,
        avg_price=avg_price,
        fee=0.0,
        ts=datetime.fromtimestamp(ts_sec, tz=timezone.utc),
    )


def test_merge_execution_state_promotes_partial_to_filled():
    partial = _report("partially_filled", 0.2, 64000, 10)
    current = merge_execution_state(None, partial)

    filled = _report("filled", 0.5, 64500, 20)
    merged = merge_execution_state(current, filled)

    assert merged["status"] == "filled"
    assert merged["filled_qty"] == 0.5
    assert merged["avg_price"] == 64500


def test_merge_execution_state_keeps_final_status_from_regression():
    filled = _report("filled", 0.5, 64500, 20)
    current = merge_execution_state(None, filled)

    late_partial = _report("partially_filled", 0.3, 64000, 30)
    merged = merge_execution_state(current, late_partial)

    assert merged["status"] == "filled"
    assert merged["filled_qty"] == 0.5


def test_merge_execution_state_keeps_highest_fee_and_latest_ts():
    current = {
        "order_id": "spot:BTCUSDT:1",
        "intent_id": "intent-1",
        "symbol": "BTCUSDT",
        "market": "spot",
        "side": 1,
        "status": "partially_filled",
        "filled_qty": 0.1,
        "avg_price": 64000,
        "fee": 1.2,
        "ts": datetime.fromtimestamp(10, tz=timezone.utc),
    }
    incoming = _report("partially_filled", 0.15, 64100, 15)
    incoming = incoming.model_copy(update={"fee": 1.1})

    merged = merge_execution_state(current, incoming)
    assert merged["fee"] == 1.2
    assert merged["ts"] == datetime.fromtimestamp(15, tz=timezone.utc)
