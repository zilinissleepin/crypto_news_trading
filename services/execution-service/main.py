from __future__ import annotations

import asyncio
import logging

from common_types import AppSettings, Streams, make_bus
from common_types.logging import configure_logging
from common_types.worker import run_stream_worker
from exchange_adapters import build_exchange_adapter

from apps.execution_service import ExecutionService

logger = logging.getLogger(__name__)


async def _pump_exchange_events(bus, service: ExecutionService, adapter) -> None:
    try:
        async for event in adapter.stream_execution_events():
            try:
                if event.get("event_type") == "alert":
                    await bus.publish(
                        Streams.RISK_ALERT,
                        {
                            "schema_version": "1.0",
                            "message": event.get("message", "Exchange stream alert"),
                            "market": event.get("market", ""),
                            "severity": event.get("severity", "warning"),
                            "ts": event.get("ts"),
                        },
                    )
                    continue

                report = service.normalize_adapter_event(event)
                if report is None:
                    continue
                await bus.publish(Streams.EXECUTION_REPORT, report.model_dump(mode="json"))
            except Exception:
                logger.exception("failed to process exchange stream event")
    except Exception:
        logger.exception("exchange execution event pump stopped")


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)

    bus = make_bus(settings)
    adapter = build_exchange_adapter(settings)
    service = ExecutionService(adapter)

    try:
        tasks = [
            run_stream_worker(
                service_name="execution-service",
                bus=bus,
                input_stream=Streams.ORDER_APPROVED,
                handler=service.handle,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
            )
        ]
        if settings.execution_mode.lower() == "live":
            tasks.append(_pump_exchange_events(bus, service, adapter))

        await asyncio.gather(*tasks)
    finally:
        close_adapter = getattr(adapter, "close", None)
        if close_adapter is not None:
            await close_adapter()
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
