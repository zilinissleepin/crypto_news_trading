from __future__ import annotations

from common_types import AppSettings, SignalEvent, Streams


class UniverseService:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        signal = SignalEvent.model_validate(payload)
        if not signal.symbol.endswith("USDT"):
            return []
        if signal.symbol not in self.settings.universe:
            return []
        return [(Streams.SIGNAL_UNIVERSE, signal.model_dump(mode="json"))]
