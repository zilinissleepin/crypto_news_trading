from __future__ import annotations

import asyncio

from common_types import AppSettings, Streams, make_bus
from common_types.logging import configure_logging
from common_types.worker import run_stream_worker

from apps.monitoring_alert_service import MonitoringAlertService, TelegramNotifier


async def _main() -> None:
    settings = AppSettings()
    configure_logging(settings.log_level)

    bus = make_bus(settings)
    service = MonitoringAlertService(TelegramNotifier(settings))

    try:
        await asyncio.gather(
            run_stream_worker(
                service_name="monitoring-alert-news",
                bus=bus,
                input_stream=Streams.NEWS_RAW,
                handler=service.handle_news,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
                start_id="$",
            ),
            run_stream_worker(
                service_name="monitoring-alert-rejected",
                bus=bus,
                input_stream=Streams.ORDER_REJECTED,
                handler=service.handle_rejected,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
                start_id="$",
            ),
            run_stream_worker(
                service_name="monitoring-alert-exec",
                bus=bus,
                input_stream=Streams.EXECUTION_REPORT,
                handler=service.handle_execution,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
                start_id="$",
            ),
            run_stream_worker(
                service_name="monitoring-alert-risk",
                bus=bus,
                input_stream=Streams.RISK_ALERT,
                handler=service.handle_risk_alert,
                poll_ms=settings.service_poll_ms,
                idle_sleep_sec=settings.service_idle_sleep_sec,
                start_id="$",
            ),
        )
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(_main())
