from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from common_types import ExecutionReport, PnLSnapshot, Streams


class PositionPnLService:
    def __init__(self):
        self.positions = defaultdict(float)
        self.avg_cost = {}
        self.realized = 0.0

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        report = ExecutionReport.model_validate(payload)
        key = (report.market, report.symbol)

        qty = report.filled_qty if report.side > 0 else -report.filled_qty
        prev_qty = self.positions[key]
        new_qty = prev_qty + qty

        if prev_qty == 0 or (prev_qty > 0 and qty > 0) or (prev_qty < 0 and qty < 0):
            prev_cost = self.avg_cost.get(key, report.avg_price)
            weighted_qty = abs(prev_qty) + abs(qty)
            self.avg_cost[key] = (prev_cost * abs(prev_qty) + report.avg_price * abs(qty)) / max(weighted_qty, 1e-9)
        else:
            entry = self.avg_cost.get(key, report.avg_price)
            closing = min(abs(prev_qty), abs(qty))
            direction = 1 if prev_qty > 0 else -1
            pnl = direction * (report.avg_price - entry) * closing
            self.realized += pnl

        self.positions[key] = new_qty
        exposure = sum(abs(v) for v in self.positions.values())
        drawdown = max(0.0, -self.realized / 100000.0)

        snapshot = PnLSnapshot(
            ts=datetime.now(timezone.utc),
            account="paper",
            unrealized=0.0,
            realized=self.realized - report.fee,
            exposure=exposure,
            drawdown=drawdown,
        )
        return [(Streams.PNL_SNAPSHOT, snapshot.model_dump(mode="json"))]
