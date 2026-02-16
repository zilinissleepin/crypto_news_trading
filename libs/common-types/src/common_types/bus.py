from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass

try:
    from redis import asyncio as redis
except ModuleNotFoundError:  # pragma: no cover - optional dependency in minimal env
    redis = None

from .config import AppSettings


@dataclass
class StreamRecord:
    id: str
    data: dict


class EventBus(ABC):
    @abstractmethod
    async def publish(self, stream: str, payload: dict) -> str:
        raise NotImplementedError

    @abstractmethod
    async def read(self, stream: str, last_id: str, block_ms: int = 1000, count: int = 100) -> list[StreamRecord]:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class RedisEventBus(EventBus):
    def __init__(self, redis_url: str):
        if redis is None:
            raise RuntimeError("redis package is not installed. Install project dependencies or use BUS_BACKEND=memory.")
        self._client = redis.from_url(redis_url, decode_responses=True)

    async def publish(self, stream: str, payload: dict) -> str:
        encoded = {"payload": json.dumps(payload)}
        return await self._client.xadd(stream, encoded)

    async def read(self, stream: str, last_id: str, block_ms: int = 1000, count: int = 100) -> list[StreamRecord]:
        response = await self._client.xread({stream: last_id}, block=block_ms, count=count)
        records: list[StreamRecord] = []
        for _, items in response:
            for item_id, fields in items:
                payload = json.loads(fields["payload"])
                records.append(StreamRecord(id=item_id, data=payload))
        return records

    async def close(self) -> None:
        await self._client.aclose()


class InMemoryEventBus(EventBus):
    def __init__(self):
        self._streams: dict[str, list[StreamRecord]] = defaultdict(list)
        self._counter = 0

    async def publish(self, stream: str, payload: dict) -> str:
        self._counter += 1
        rec_id = f"{self._counter}-0"
        self._streams[stream].append(StreamRecord(id=rec_id, data=payload))
        return rec_id

    async def read(self, stream: str, last_id: str, block_ms: int = 1000, count: int = 100) -> list[StreamRecord]:
        del block_ms
        stream_events = self._streams.get(stream, [])
        last_num = int(last_id.split("-")[0]) if "-" in last_id else 0
        out: list[StreamRecord] = []
        for event in stream_events:
            if int(event.id.split("-")[0]) > last_num:
                out.append(event)
            if len(out) >= count:
                break
        return out

    async def close(self) -> None:
        return None


def make_bus(settings: AppSettings) -> EventBus:
    if settings.bus_backend.lower() in {"memory", "inmemory"}:
        return InMemoryEventBus()
    return RedisEventBus(settings.redis_url)
