from __future__ import annotations

from datetime import datetime, timezone
from random import uniform
from uuid import uuid4

from common_types.models import ExecutionReport, OrderIntent

from .base import ExchangeAdapter


class SimulatedExchangeAdapter(ExchangeAdapter):
    def __init__(self):
        self._base_prices: dict[str, float] = {
            "BTCUSDT": 65000.0,
            "ETHUSDT": 3200.0,
            "BNBUSDT": 580.0,
            "SOLUSDT": 140.0,
            "XRPUSDT": 0.62,
            "ADAUSDT": 0.47,
            "DOGEUSDT": 0.12,
            "LINKUSDT": 19.0,
            "AVAXUSDT": 34.0,
            "TONUSDT": 6.8,
        }
        self._positions: dict[tuple[str, str], float] = {}

    def _get_price(self, symbol: str) -> float:
        base = self._base_prices.get(symbol, 10.0)
        return max(0.0001, base * (1 + uniform(-0.0015, 0.0015)))

    async def place_order(self, intent: OrderIntent) -> ExecutionReport:
        px = self._get_price(intent.symbol)
        qty = intent.qty_usd / px
        fee = intent.qty_usd * 0.0004

        key = (intent.market, intent.symbol)
        signed_qty = qty if intent.side > 0 else -qty
        self._positions[key] = self._positions.get(key, 0.0) + signed_qty

        return ExecutionReport(
            order_id=f"paper-{uuid4().hex[:16]}",
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            market=intent.market,
            side=intent.side,
            status="filled",
            filled_qty=qty,
            avg_price=px,
            fee=fee,
            ts=datetime.now(timezone.utc),
        )

    async def cancel_order(self, order_id: str) -> bool:
        del order_id
        return True

    async def fetch_positions(self) -> list[dict]:
        out = []
        for (market, symbol), qty in self._positions.items():
            px = self._base_prices.get(symbol, 10.0)
            out.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "qty": qty,
                    "notional_usd": abs(qty) * px,
                }
            )
        return out

    async def stream_execution_events(self):
        if False:
            yield {}
