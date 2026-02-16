from __future__ import annotations

import json
from typing import Any

from common_types import ExecutionReport, NewsEvent, OrderIntent, PnLSnapshot, RiskDecision

try:
    import asyncpg
except ModuleNotFoundError:  # pragma: no cover
    asyncpg = None


STATUS_RANK = {
    "new": 0,
    "partially_filled": 1,
    "filled": 3,
    "rejected": 3,
    "canceled": 3,
}


def merge_execution_state(current: dict | None, incoming: ExecutionReport) -> dict:
    if current is None:
        return {
            "order_id": incoming.order_id,
            "intent_id": incoming.intent_id,
            "symbol": incoming.symbol,
            "market": incoming.market,
            "side": incoming.side,
            "status": incoming.status,
            "filled_qty": incoming.filled_qty,
            "avg_price": incoming.avg_price,
            "fee": incoming.fee,
            "ts": incoming.ts,
        }

    current_rank = STATUS_RANK.get(str(current.get("status", "new")), 0)
    incoming_rank = STATUS_RANK.get(incoming.status, 0)

    status = str(current.get("status", incoming.status))
    if incoming_rank > current_rank or (incoming_rank == current_rank and incoming.ts >= current.get("ts", incoming.ts)):
        status = incoming.status

    current_filled = float(current.get("filled_qty", 0.0))
    current_fee = float(current.get("fee", 0.0))
    current_avg_price = float(current.get("avg_price", 0.0))
    current_ts = current.get("ts", incoming.ts)

    merged_filled = max(current_filled, incoming.filled_qty)
    merged_fee = max(current_fee, incoming.fee)
    merged_ts = max(current_ts, incoming.ts)
    merged_avg_price = incoming.avg_price if incoming.filled_qty >= current_filled else current_avg_price

    return {
        "order_id": incoming.order_id,
        "intent_id": incoming.intent_id or str(current.get("intent_id", "")),
        "symbol": incoming.symbol,
        "market": incoming.market,
        "side": incoming.side,
        "status": status,
        "filled_qty": merged_filled,
        "avg_price": merged_avg_price,
        "fee": merged_fee,
        "ts": merged_ts,
    }


class PostgresPersistenceService:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self) -> None:
        if asyncpg is None:
            raise RuntimeError("asyncpg is required for persistence-service. Install dependencies first.")
        self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def _execute(self, query: str, *args: Any) -> None:
        if self.pool is None:
            raise RuntimeError("persistence service is not connected")
        async with self.pool.acquire() as conn:
            await conn.execute(query, *args)

    async def _fetchrow(self, query: str, *args: Any):
        if self.pool is None:
            raise RuntimeError("persistence service is not connected")
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def handle_news(self, payload: dict) -> list[tuple[str, dict]]:
        event = NewsEvent.model_validate(payload)
        await self._execute(
            """
            INSERT INTO news_events(event_id, source, published_at, title, content, lang, url, dedup_hash)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT(event_id) DO UPDATE SET
              source = EXCLUDED.source,
              published_at = EXCLUDED.published_at,
              title = EXCLUDED.title,
              content = EXCLUDED.content,
              lang = EXCLUDED.lang,
              url = EXCLUDED.url,
              dedup_hash = EXCLUDED.dedup_hash
            """,
            event.event_id,
            event.source,
            event.published_at,
            event.title,
            event.content,
            event.lang,
            event.url,
            event.dedup_hash,
        )
        return []

    async def handle_intent(self, payload: dict) -> list[tuple[str, dict]]:
        intent = OrderIntent.model_validate(payload)
        await self._execute(
            """
            INSERT INTO order_intents(intent_id, event_id, symbol, market, side, qty_usd, max_slippage_bps, reason)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT(intent_id) DO UPDATE SET
              event_id = EXCLUDED.event_id,
              symbol = EXCLUDED.symbol,
              market = EXCLUDED.market,
              side = EXCLUDED.side,
              qty_usd = EXCLUDED.qty_usd,
              max_slippage_bps = EXCLUDED.max_slippage_bps,
              reason = EXCLUDED.reason
            """,
            intent.intent_id,
            intent.event_id,
            intent.symbol,
            intent.market,
            intent.side,
            intent.qty_usd,
            intent.max_slippage_bps,
            intent.reason,
        )
        return []

    async def handle_risk_decision(self, payload: dict) -> list[tuple[str, dict]]:
        decision = RiskDecision.model_validate(payload)
        await self._execute(
            """
            INSERT INTO risk_decisions(intent_id, allow, reason_code, capped_qty_usd)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(intent_id) DO UPDATE SET
              allow = EXCLUDED.allow,
              reason_code = EXCLUDED.reason_code,
              capped_qty_usd = EXCLUDED.capped_qty_usd
            """,
            decision.intent_id,
            decision.allow,
            decision.reason_code,
            decision.capped_qty_usd,
        )
        return []

    async def handle_execution(self, payload: dict) -> list[tuple[str, dict]]:
        report = ExecutionReport.model_validate(payload)
        report_payload_json = json.dumps(report.model_dump(mode="json"))
        await self._execute(
            """
            INSERT INTO execution_report_events(
              order_id, intent_id, symbol, market, side, status, filled_qty, avg_price, fee, ts, payload
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb)
            ON CONFLICT(order_id, status, filled_qty, avg_price, fee, ts) DO NOTHING
            """,
            report.order_id,
            report.intent_id,
            report.symbol,
            report.market,
            report.side,
            report.status,
            report.filled_qty,
            report.avg_price,
            report.fee,
            report.ts,
            report_payload_json,
        )

        current = await self._fetchrow(
            """
            SELECT order_id, intent_id, symbol, market, side, status, filled_qty, avg_price, fee, ts
            FROM execution_reports
            WHERE order_id = $1
            """,
            report.order_id,
        )
        merged = merge_execution_state(dict(current) if current is not None else None, report)

        await self._execute(
            """
            INSERT INTO execution_reports(order_id, intent_id, symbol, market, side, filled_qty, avg_price, fee, status, ts)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT(order_id) DO UPDATE SET
              intent_id = EXCLUDED.intent_id,
              symbol = EXCLUDED.symbol,
              market = EXCLUDED.market,
              side = EXCLUDED.side,
              filled_qty = EXCLUDED.filled_qty,
              avg_price = EXCLUDED.avg_price,
              fee = EXCLUDED.fee,
              status = EXCLUDED.status,
              ts = EXCLUDED.ts
            """,
            merged["order_id"],
            merged["intent_id"],
            merged["symbol"],
            merged["market"],
            merged["side"],
            merged["filled_qty"],
            merged["avg_price"],
            merged["fee"],
            merged["status"],
            merged["ts"],
        )
        return []

    async def handle_pnl(self, payload: dict) -> list[tuple[str, dict]]:
        snapshot = PnLSnapshot.model_validate(payload)
        await self._execute(
            """
            INSERT INTO pnl_snapshots(ts, account, unrealized, realized, exposure, drawdown)
            VALUES($1,$2,$3,$4,$5,$6)
            """,
            snapshot.ts,
            snapshot.account,
            snapshot.unrealized,
            snapshot.realized,
            snapshot.exposure,
            snapshot.drawdown,
        )
        return []
