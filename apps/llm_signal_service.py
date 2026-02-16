from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ModuleNotFoundError:  # pragma: no cover
    def retry(*args, **kwargs):  # type: ignore
        del args, kwargs
        def _decorator(fn):
            return fn
        return _decorator

    def stop_after_attempt(*args, **kwargs):  # type: ignore
        del args, kwargs
        return None

    def wait_exponential(*args, **kwargs):  # type: ignore
        del args, kwargs
        return None

from common_types import AppSettings, EntityEvent, SignalEvent, Streams

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = {"approval", "surge", "adoption", "partnership", "listing", "inflow", "upgrade"}
NEGATIVE_KEYWORDS = {"hack", "exploit", "lawsuit", "ban", "outflow", "delist", "investigation"}


class LLMProvider:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._client = None
        if settings.openai_api_key:
            from openai import AsyncOpenAI

            kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._client = AsyncOpenAI(**kwargs)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def infer(self, title: str, content: str, symbol: str) -> dict:
        if self._client is None:
            return self._heuristic(title, content)

        prompt = (
            "You are a crypto event analyst. Return strict JSON with keys: "
            "side (-1,0,1), strength (0..1), confidence (0..1), horizon_min (int), rationale (short)."
            f"\nSymbol: {symbol}\nTitle: {title}\nContent: {content[:1500]}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            text = (response.choices[0].message.content or "").strip()
            parsed = self._parse_json_text(text)
            if parsed is None:
                raise ValueError("model output is not valid json")
            return parsed
        except Exception:
            logger.exception("openai inference failed, fallback heuristic")
            return self._heuristic(title, content)

    def _parse_json_text(self, text: str) -> dict | None:
        if not text:
            return None

        # First try strict JSON parse.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Then try extracting from fenced code blocks or mixed content.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    def _heuristic(self, title: str, content: str) -> dict:
        text = f"{title} {content}".lower()
        pos = sum(1 for k in POSITIVE_KEYWORDS if k in text)
        neg = sum(1 for k in NEGATIVE_KEYWORDS if k in text)

        side = 0
        if pos > neg:
            side = 1
        elif neg > pos:
            side = -1

        edge = abs(pos - neg)
        strength = min(1.0, 0.4 + edge * 0.15)
        confidence = min(0.95, 0.55 + edge * 0.1)
        horizon_min = 60 if edge < 2 else 180

        return {
            "side": side,
            "strength": strength,
            "confidence": confidence,
            "horizon_min": horizon_min,
            "rationale": f"heuristic pos={pos} neg={neg}",
        }


class LLMSignalService:
    def __init__(self, settings: AppSettings, provider: LLMProvider):
        self.settings = settings
        self.provider = provider

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        event = EntityEvent.model_validate(payload)
        outputs: list[tuple[str, dict]] = []

        for symbol in event.symbols:
            inference = await self.provider.infer(event.title, event.content, symbol)
            signal = SignalEvent(
                event_id=event.event_id,
                symbol=symbol,
                side=int(inference.get("side", 0)),
                strength=float(inference.get("strength", 0.0)),
                confidence=float(inference.get("confidence", 0.0)),
                horizon_min=int(inference.get("horizon_min", 60)),
                ttl_sec=self.settings.default_event_ttl_sec,
                rationale=str(inference.get("rationale", "")),
                generated_at=datetime.now(timezone.utc),
            )
            outputs.append((Streams.SIGNAL_RAW, signal.model_dump(mode="json")))

        return outputs
