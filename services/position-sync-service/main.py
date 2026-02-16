from __future__ import annotations

import asyncio

from common_types import AppSettings, make_bus
from common_types.logging import configure_logging
from exchange_adapters import build_exchange_adapter
from feature_store import MemoryTradingStateStore, RedisTradingStateStore

from apps.position_sync_service import PositionSyncService


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)

    bus = make_bus(settings)
    adapter = build_exchange_adapter(settings)
    state = MemoryTradingStateStore() if settings.bus_backend in {"memory", "inmemory"} else RedisTradingStateStore(settings.redis_url)

    service = PositionSyncService(settings, adapter, state, bus)
    try:
        await service.run_forever()
    finally:
        close_adapter = getattr(adapter, "close", None)
        if close_adapter is not None:
            await close_adapter()
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
