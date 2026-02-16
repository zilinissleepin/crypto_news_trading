from __future__ import annotations

from common_types import AppSettings, OrderIntent, PnLSnapshot, RiskDecision, Streams
from feature_store import TradingStateStore


class RiskService:
    def __init__(self, settings: AppSettings, state: TradingStateStore):
        self.settings = settings
        self.state = state
        self.kill_switch = False
        self._last_snapshot_realized = 0.0

    async def _daily_drawdown_breached(self) -> bool:
        realized = await self.state.get_daily_realized_pnl()
        drawdown_limit = self.settings.account_equity_usd * self.settings.max_daily_drawdown_pct
        return realized <= -drawdown_limit

    async def handle_order_intent(self, payload: dict) -> list[tuple[str, dict]]:
        intent = OrderIntent.model_validate(payload)
        if self.kill_switch or await self._daily_drawdown_breached():
            self.kill_switch = True
            decision = RiskDecision(
                intent_id=intent.intent_id,
                allow=False,
                reason_code="DAILY_DRAWDOWN_BREACH",
                capped_qty_usd=0.0,
            )
            return [(Streams.ORDER_REJECTED, decision.model_dump(mode="json"))]

        symbol_limit = self.settings.account_equity_usd * self.settings.max_symbol_exposure_pct
        total_limit = self.settings.account_equity_usd * self.settings.max_total_exposure_pct
        market_limit_pct = self.settings.max_spot_exposure_pct if intent.market == "spot" else self.settings.max_perp_exposure_pct
        market_limit = self.settings.account_equity_usd * market_limit_pct
        side_limit_pct = self.settings.max_long_exposure_pct if intent.side > 0 else self.settings.max_short_exposure_pct
        side_limit = self.settings.account_equity_usd * side_limit_pct

        current_symbol = await self.state.get_symbol_exposure(intent.symbol)
        current_total = await self.state.get_total_exposure()
        current_market = await self.state.get_market_exposure(intent.market)
        current_side = await self.state.get_side_exposure(intent.side)

        allowed_by_symbol = max(0.0, symbol_limit - current_symbol)
        allowed_by_total = max(0.0, total_limit - current_total)
        allowed_by_market = max(0.0, market_limit - current_market)
        allowed_by_side = max(0.0, side_limit - current_side)
        cap = min(intent.qty_usd, allowed_by_symbol, allowed_by_total, allowed_by_market, allowed_by_side)

        if cap <= 0:
            if allowed_by_symbol <= 0:
                reason_code = "SYMBOL_EXPOSURE_LIMIT"
            elif allowed_by_market <= 0:
                reason_code = "MARKET_EXPOSURE_LIMIT"
            elif allowed_by_side <= 0:
                reason_code = "SIDE_EXPOSURE_LIMIT"
            else:
                reason_code = "TOTAL_EXPOSURE_LIMIT"
            decision = RiskDecision(
                intent_id=intent.intent_id,
                allow=False,
                reason_code=reason_code,
                capped_qty_usd=0.0,
            )
            return [(Streams.ORDER_REJECTED, decision.model_dump(mode="json"))]

        approved = intent.model_copy(update={"qty_usd": cap})
        await self.state.add_symbol_exposure(intent.symbol, cap)
        await self.state.add_total_exposure(cap)
        await self.state.add_market_exposure(intent.market, cap)
        await self.state.add_side_exposure(intent.side, cap)
        return [(Streams.ORDER_APPROVED, approved.model_dump(mode="json"))]

    async def handle_pnl_snapshot(self, payload: dict) -> list[tuple[str, dict]]:
        snapshot = PnLSnapshot.model_validate(payload)
        delta_realized = snapshot.realized - self._last_snapshot_realized
        self._last_snapshot_realized = snapshot.realized
        await self.state.add_daily_realized_pnl(delta_realized)
        if await self._daily_drawdown_breached():
            self.kill_switch = True
            return [
                (
                    Streams.RISK_ALERT,
                    {
                        "schema_version": "1.0",
                        "message": "Daily drawdown breached. Strategy halted.",
                        "drawdown": snapshot.drawdown,
                    },
                )
            ]
        return []
