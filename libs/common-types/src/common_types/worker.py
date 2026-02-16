from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .bus import EventBus

logger = logging.getLogger(__name__)


Handler = Callable[[dict], Awaitable[list[tuple[str, dict]]]]


async def run_stream_worker(
    *,
    service_name: str,
    bus: EventBus,
    input_stream: str,
    handler: Handler,
    poll_ms: int = 1000,
    idle_sleep_sec: float = 0.2,
    start_id: str = "0-0",
) -> None:
    last_id = start_id
    logger.info("%s started. input_stream=%s", service_name, input_stream)
    while True:
        records = await bus.read(input_stream, last_id=last_id, block_ms=poll_ms)
        if not records:
            await asyncio.sleep(idle_sleep_sec)
            continue

        for record in records:
            try:
                outputs = await handler(record.data)
                for out_stream, payload in outputs:
                    await bus.publish(out_stream, payload)
                last_id = record.id
            except Exception:
                logger.exception("%s failed to process record id=%s", service_name, record.id)
