from __future__ import annotations

import time
from abc import ABC, abstractmethod

try:
    from redis import asyncio as redis
except ModuleNotFoundError:  # pragma: no cover
    redis = None


class DedupStore(ABC):
    @abstractmethod
    async def seen_or_add(self, key: str, ttl_sec: int) -> bool:
        raise NotImplementedError


class MemoryDedupStore(DedupStore):
    def __init__(self):
        self._items: dict[str, float] = {}

    async def seen_or_add(self, key: str, ttl_sec: int) -> bool:
        now = time.time()
        expiry = self._items.get(key)
        if expiry and expiry > now:
            return True
        self._items[key] = now + ttl_sec
        return False


class RedisDedupStore(DedupStore):
    def __init__(self, redis_url: str, namespace: str = "dedup"):
        if redis is None:
            raise RuntimeError("redis package is not installed. Install project dependencies or use memory dedup store.")
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._namespace = namespace

    async def seen_or_add(self, key: str, ttl_sec: int) -> bool:
        namespaced_key = f"{self._namespace}:{key}"
        created = await self._client.set(namespaced_key, "1", ex=ttl_sec, nx=True)
        return created is None
