from __future__ import annotations

from datetime import datetime, timezone

from common_types import AppSettings, SignalEvent, Streams
from common_types.models import is_stale


class SignalFusionService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._last_signal: dict[str, SignalEvent] = {}
        self._conflict_window_sec = 30 * 60

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        signal = SignalEvent.model_validate(payload)

        if signal.side == 0:
            return []
        if signal.confidence < self.settings.min_signal_confidence:
            return []
        if is_stale(signal):
            return []

        prev = self._last_signal.get(signal.symbol)
        if prev:
            delta = (signal.generated_at - prev.generated_at).total_seconds()
            opposite = signal.side != prev.side
            close_strength = abs(signal.strength - prev.strength) < 0.2
            if opposite and delta <= self._conflict_window_sec and close_strength:
                return []

        fused_strength = min(1.0, signal.strength * (0.8 + 0.2 * signal.confidence))
        fused = signal.model_copy(update={
            "strength": fused_strength,
            "generated_at": datetime.now(timezone.utc),
            "rationale": f"fused: {signal.rationale}",
        })
        self._last_signal[signal.symbol] = fused
        return [(Streams.SIGNAL_TRADEABLE, fused.model_dump(mode="json"))]
