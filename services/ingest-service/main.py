from __future__ import annotations

import asyncio

from common_types import AppSettings, make_bus
from common_types.logging import configure_logging
from feature_store import MemoryDedupStore, RedisDedupStore

from apps.ingest_service import IngestService


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)
    bus = make_bus(settings)
    dedup = MemoryDedupStore() if settings.bus_backend in {"memory", "inmemory"} else RedisDedupStore(settings.redis_url)

    service = IngestService(settings, bus, dedup)
    try:
        await service.run_forever(interval_sec=30)
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
