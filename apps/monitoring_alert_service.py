from __future__ import annotations

import logging

import httpx

from common_types import AppSettings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, settings: AppSettings):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id

    async def send(self, text: str) -> None:
        if not self.token or not self.chat_id:
            logger.info("alert: %s", text)
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload)
        except Exception:
            logger.exception("telegram send failed")


class MonitoringAlertService:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    async def handle_rejected(self, payload: dict) -> list[tuple[str, dict]]:
        message = (
            f"[REJECTED] intent={payload.get('intent_id')} reason={payload.get('reason_code')} "
            f"cap={payload.get('capped_qty_usd')}"
        )
        await self.notifier.send(message)
        return []

    async def handle_execution(self, payload: dict) -> list[tuple[str, dict]]:
        message = (
            f"[EXEC] order={payload.get('order_id')} {payload.get('symbol')} "
            f"status={payload.get('status')} qty={payload.get('filled_qty')} px={payload.get('avg_price')}"
        )
        await self.notifier.send(message)
        return []

    async def handle_risk_alert(self, payload: dict) -> list[tuple[str, dict]]:
        await self.notifier.send(f"[RISK] {payload.get('message')}")
        return []
