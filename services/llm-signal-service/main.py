from __future__ import annotations

import asyncio

from common_types import AppSettings, Streams, make_bus
from common_types.logging import configure_logging
from common_types.worker import run_stream_worker

from apps.llm_signal_service import LLMProvider, LLMSignalService


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)

    bus = make_bus(settings)
    provider = LLMProvider(settings)
    service = LLMSignalService(settings, provider)

    try:
        await run_stream_worker(
            service_name="llm-signal-service",
            bus=bus,
            input_stream=Streams.NEWS_ENTITY,
            handler=service.handle,
            poll_ms=settings.service_poll_ms,
            idle_sleep_sec=settings.service_idle_sleep_sec,
        )
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
