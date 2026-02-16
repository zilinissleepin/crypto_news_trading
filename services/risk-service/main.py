from __future__ import annotations

import asyncio

from common_types import AppSettings, Streams, make_bus
from common_types.logging import configure_logging
from common_types.worker import run_stream_worker
from feature_store import MemoryTradingStateStore, RedisTradingStateStore

from apps.risk_service import RiskService


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)

    bus = make_bus(settings)
    state = MemoryTradingStateStore() if settings.bus_backend in {"memory", "inmemory"} else RedisTradingStateStore(settings.redis_url)
    service = RiskService(settings, state)

    try:
        await asyncio.gather(
            run_stream_worker(
                service_name="risk-service-intent",
                bus=bus,
                input_stream=Streams.ORDER_INTENT,
                handler=service.handle_order_intent,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
            run_stream_worker(
                service_name="risk-service-pnl",
                bus=bus,
                input_stream=Streams.PNL_SNAPSHOT,
                handler=service.handle_pnl_snapshot,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
        )
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
