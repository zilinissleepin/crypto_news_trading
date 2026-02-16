from __future__ import annotations

from abc import ABC, abstractmethod

from common_types.models import ExecutionReport, OrderIntent


class ExchangeAdapter(ABC):
    @abstractmethod
    async def place_order(self, intent: OrderIntent) -> ExecutionReport:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fetch_positions(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def stream_execution_events(self):
        raise NotImplementedError
