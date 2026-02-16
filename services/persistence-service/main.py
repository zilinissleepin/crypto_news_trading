from __future__ import annotations

import asyncio

from common_types import AppSettings, Streams, make_bus
from common_types.logging import configure_logging
from common_types.worker import run_stream_worker

from apps.persistence_service import PostgresPersistenceService


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)

    bus = make_bus(settings)
    service = PostgresPersistenceService(settings.postgres_dsn)
    await service.connect()

    try:
        await asyncio.gather(
            run_stream_worker(
                service_name="persistence-news",
                bus=bus,
                input_stream=Streams.NEWS_RAW,
                handler=service.handle_news,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
            run_stream_worker(
                service_name="persistence-intent",
                bus=bus,
                input_stream=Streams.ORDER_INTENT,
                handler=service.handle_intent,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
            run_stream_worker(
                service_name="persistence-rejected",
                bus=bus,
                input_stream=Streams.ORDER_REJECTED,
                handler=service.handle_risk_decision,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
            run_stream_worker(
                service_name="persistence-execution",
                bus=bus,
                input_stream=Streams.EXECUTION_REPORT,
                handler=service.handle_execution,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
            run_stream_worker(
                service_name="persistence-pnl",
                bus=bus,
                input_stream=Streams.PNL_SNAPSHOT,
                handler=service.handle_pnl,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            ),
        )
    finally:
        await service.close()
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
