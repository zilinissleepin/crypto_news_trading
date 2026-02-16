from __future__ import annotations

from common_types import ExecutionReport, OrderIntent, Streams
from exchange_adapters import ExchangeAdapter


class ExecutionService:
    def __init__(self, adapter: ExchangeAdapter):
        self.adapter = adapter
        self._processed_intents: set[str] = set()
        self._seen_execution_keys: set[tuple[str, str, float]] = set()

    def _is_duplicate_report(self, report: ExecutionReport) -> bool:
        key = (report.order_id, report.status, round(report.filled_qty, 10))
        if key in self._seen_execution_keys:
            return True
        self._seen_execution_keys.add(key)
        return False

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        intent = OrderIntent.model_validate(payload)
        if intent.intent_id in self._processed_intents:
            return []
        report: ExecutionReport = await self.adapter.place_order(intent)
        self._processed_intents.add(intent.intent_id)
        if self._is_duplicate_report(report):
            return []
        return [(Streams.EXECUTION_REPORT, report.model_dump(mode="json"))]

    def normalize_adapter_event(self, payload: dict) -> ExecutionReport | None:
        report = ExecutionReport.model_validate(payload)
        if self._is_duplicate_report(report):
            return None
        return report
