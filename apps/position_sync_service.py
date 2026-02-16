from __future__ import annotations

import asyncio
import logging

from common_types import AppSettings, Streams
from common_types.bus import EventBus
from exchange_adapters import ExchangeAdapter
from feature_store import TradingStateStore

logger = logging.getLogger(__name__)


def _safe_notional(position: dict) -> float:
    notional = position.get("notional_usd")
    if notional is None:
        return abs(float(position.get("qty", 0.0)))
    return abs(float(notional))


class PositionSyncService:
    def __init__(self, settings: AppSettings, adapter: ExchangeAdapter, state: TradingStateStore, bus: EventBus):
        self.settings = settings
        self.adapter = adapter
        self.state = state
        self.bus = bus

    def build_snapshot(self, positions: list[dict]) -> dict:
        symbol_exposure: dict[str, float] = {}
        market_exposure: dict[str, float] = {}
        side_exposure: dict[str, float] = {"long": 0.0, "short": 0.0}

        for pos in positions:
            symbol = str(pos.get("symbol", "")).upper()
            market = str(pos.get("market", "")).lower()
            qty = float(pos.get("qty", 0.0))
            if not symbol or not market:
                continue

            notional = _safe_notional(pos)
            if notional <= 0:
                continue

            symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + notional
            market_exposure[market] = market_exposure.get(market, 0.0) + notional

            if qty >= 0:
                side_exposure["long"] += notional
            else:
                side_exposure["short"] += notional

        total_exposure = sum(market_exposure.values())
        return {
            "symbol_exposure": symbol_exposure,
            "market_exposure": market_exposure,
            "side_exposure": side_exposure,
            "total_exposure": total_exposure,
        }

    async def run_once(self) -> dict:
        if self.settings.execution_mode.lower() != "live":
            return {"skipped": True, "reason": "execution_mode_not_live"}

        positions = await self.adapter.fetch_positions()
        snapshot = self.build_snapshot(positions)

        current_total = await self.state.get_total_exposure()
        desired_total = float(snapshot["total_exposure"])
        equity = max(self.settings.account_equity_usd, 1.0)
        drift_pct = abs(desired_total - current_total) / equity

        if drift_pct >= self.settings.position_sync_drift_alert_pct:
            message = (
                "Position sync drift detected and reconciled. "
                f"current_total={current_total:.2f} desired_total={desired_total:.2f} drift_pct={drift_pct:.4f}"
            )
            await self.bus.publish(
                Streams.RISK_ALERT,
                {
                    "schema_version": "1.0",
                    "message": message,
                    "severity": "warning",
                    "source": "position-sync-service",
                },
            )

        await self.state.replace_exposure_snapshot(
            symbol_exposure=snapshot["symbol_exposure"],
            market_exposure=snapshot["market_exposure"],
            side_exposure=snapshot["side_exposure"],
            total_exposure=snapshot["total_exposure"],
        )

        return {
            "skipped": False,
            "positions": len(positions),
            "total_exposure": desired_total,
            "drift_pct": drift_pct,
        }

    async def run_forever(self) -> None:
        while True:
            try:
                result = await self.run_once()
                logger.info("position sync result=%s", result)
            except Exception:
                logger.exception("position sync failed")
            await asyncio.sleep(max(5, self.settings.position_sync_interval_sec))
