from __future__ import annotations

from uuid import uuid4

from common_types import AppSettings, OrderIntent, SignalEvent, Streams


class PortfolioService:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        signal = SignalEvent.model_validate(payload)
        base_risk_capital = self.settings.account_equity_usd * self.settings.risk_per_trade_pct
        qty_usd = max(10.0, base_risk_capital * max(0.2, signal.strength))

        market = "spot" if signal.side > 0 else "perp"

        intent = OrderIntent(
            intent_id=uuid4().hex[:20],
            event_id=signal.event_id,
            symbol=signal.symbol,
            market=market,
            side=signal.side,
            qty_usd=qty_usd,
            max_slippage_bps=self.settings.max_slippage_bps,
            reason=f"signal strength={signal.strength:.3f} conf={signal.confidence:.3f}",
        )
        return [(Streams.ORDER_INTENT, intent.model_dump(mode="json"))]
