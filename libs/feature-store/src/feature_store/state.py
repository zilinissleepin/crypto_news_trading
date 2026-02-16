from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

try:
    from redis import asyncio as redis
except ModuleNotFoundError:  # pragma: no cover
    redis = None


class TradingStateStore(ABC):
    @abstractmethod
    async def get_symbol_exposure(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    async def add_symbol_exposure(self, symbol: str, delta: float) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_total_exposure(self) -> float:
        raise NotImplementedError

    @abstractmethod
    async def add_total_exposure(self, delta: float) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_market_exposure(self, market: str) -> float:
        raise NotImplementedError

    @abstractmethod
    async def add_market_exposure(self, market: str, delta: float) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_side_exposure(self, side: int) -> float:
        raise NotImplementedError

    @abstractmethod
    async def add_side_exposure(self, side: int, delta: float) -> None:
        raise NotImplementedError

    @abstractmethod
    async def replace_exposure_snapshot(
        self,
        *,
        symbol_exposure: dict[str, float],
        market_exposure: dict[str, float],
        side_exposure: dict[str, float],
        total_exposure: float,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_daily_realized_pnl(self) -> float:
        raise NotImplementedError

    @abstractmethod
    async def add_daily_realized_pnl(self, delta: float) -> None:
        raise NotImplementedError


class MemoryTradingStateStore(TradingStateStore):
    def __init__(self):
        self._symbol_exposure = defaultdict(float)
        self._total_exposure = 0.0
        self._market_exposure = defaultdict(float)
        self._side_exposure = defaultdict(float)
        self._daily_realized_pnl = 0.0

    async def get_symbol_exposure(self, symbol: str) -> float:
        return self._symbol_exposure[symbol.upper()]

    async def add_symbol_exposure(self, symbol: str, delta: float) -> None:
        self._symbol_exposure[symbol.upper()] += delta

    async def get_total_exposure(self) -> float:
        return self._total_exposure

    async def add_total_exposure(self, delta: float) -> None:
        self._total_exposure += delta

    async def get_market_exposure(self, market: str) -> float:
        return self._market_exposure[market.lower()]

    async def add_market_exposure(self, market: str, delta: float) -> None:
        self._market_exposure[market.lower()] += delta

    async def get_side_exposure(self, side: int) -> float:
        key = "long" if side > 0 else "short"
        return self._side_exposure[key]

    async def add_side_exposure(self, side: int, delta: float) -> None:
        key = "long" if side > 0 else "short"
        self._side_exposure[key] += delta

    async def replace_exposure_snapshot(
        self,
        *,
        symbol_exposure: dict[str, float],
        market_exposure: dict[str, float],
        side_exposure: dict[str, float],
        total_exposure: float,
    ) -> None:
        self._symbol_exposure.clear()
        for symbol, exposure in symbol_exposure.items():
            self._symbol_exposure[symbol.upper()] = float(exposure)

        self._market_exposure.clear()
        for market, exposure in market_exposure.items():
            self._market_exposure[market.lower()] = float(exposure)

        self._side_exposure.clear()
        self._side_exposure["long"] = float(side_exposure.get("long", 0.0))
        self._side_exposure["short"] = float(side_exposure.get("short", 0.0))
        self._total_exposure = float(total_exposure)

    async def get_daily_realized_pnl(self) -> float:
        return self._daily_realized_pnl

    async def add_daily_realized_pnl(self, delta: float) -> None:
        self._daily_realized_pnl += delta


class RedisTradingStateStore(TradingStateStore):
    def __init__(self, redis_url: str, namespace: str = "state"):
        if redis is None:
            raise RuntimeError("redis package is not installed. Install project dependencies or use memory state store.")
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._namespace = namespace

    def _symbol_key(self, symbol: str) -> str:
        return f"{self._namespace}:symbol_exposure:{symbol.upper()}"

    def _total_key(self) -> str:
        return f"{self._namespace}:total_exposure"

    def _market_key(self, market: str) -> str:
        return f"{self._namespace}:market_exposure:{market.lower()}"

    def _side_key(self, side: int) -> str:
        side_name = "long" if side > 0 else "short"
        return f"{self._namespace}:side_exposure:{side_name}"

    def _daily_pnl_key(self) -> str:
        return f"{self._namespace}:daily_realized_pnl"

    async def get_symbol_exposure(self, symbol: str) -> float:
        value = await self._client.get(self._symbol_key(symbol))
        return float(value) if value is not None else 0.0

    async def add_symbol_exposure(self, symbol: str, delta: float) -> None:
        await self._client.incrbyfloat(self._symbol_key(symbol), delta)

    async def get_total_exposure(self) -> float:
        value = await self._client.get(self._total_key())
        return float(value) if value is not None else 0.0

    async def add_total_exposure(self, delta: float) -> None:
        await self._client.incrbyfloat(self._total_key(), delta)

    async def get_market_exposure(self, market: str) -> float:
        value = await self._client.get(self._market_key(market))
        return float(value) if value is not None else 0.0

    async def add_market_exposure(self, market: str, delta: float) -> None:
        await self._client.incrbyfloat(self._market_key(market), delta)

    async def get_side_exposure(self, side: int) -> float:
        value = await self._client.get(self._side_key(side))
        return float(value) if value is not None else 0.0

    async def add_side_exposure(self, side: int, delta: float) -> None:
        await self._client.incrbyfloat(self._side_key(side), delta)

    async def replace_exposure_snapshot(
        self,
        *,
        symbol_exposure: dict[str, float],
        market_exposure: dict[str, float],
        side_exposure: dict[str, float],
        total_exposure: float,
    ) -> None:
        symbol_pattern = f"{self._namespace}:symbol_exposure:*"
        market_pattern = f"{self._namespace}:market_exposure:*"
        side_pattern = f"{self._namespace}:side_exposure:*"

        old_symbol_keys = [key async for key in self._client.scan_iter(match=symbol_pattern)]
        old_market_keys = [key async for key in self._client.scan_iter(match=market_pattern)]
        old_side_keys = [key async for key in self._client.scan_iter(match=side_pattern)]

        if old_symbol_keys:
            await self._client.delete(*old_symbol_keys)
        if old_market_keys:
            await self._client.delete(*old_market_keys)
        if old_side_keys:
            await self._client.delete(*old_side_keys)

        pipe = self._client.pipeline()
        for symbol, exposure in symbol_exposure.items():
            pipe.set(self._symbol_key(symbol), str(float(exposure)))
        for market, exposure in market_exposure.items():
            pipe.set(self._market_key(market), str(float(exposure)))

        pipe.set(self._side_key(1), str(float(side_exposure.get("long", 0.0))))
        pipe.set(self._side_key(-1), str(float(side_exposure.get("short", 0.0))))
        pipe.set(self._total_key(), str(float(total_exposure)))
        await pipe.execute()

    async def get_daily_realized_pnl(self) -> float:
        value = await self._client.get(self._daily_pnl_key())
        return float(value) if value is not None else 0.0

    async def add_daily_realized_pnl(self, delta: float) -> None:
        await self._client.incrbyfloat(self._daily_pnl_key(), delta)
