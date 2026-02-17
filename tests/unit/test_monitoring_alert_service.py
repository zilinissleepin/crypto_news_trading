import asyncio
from datetime import datetime, timezone

from apps.monitoring_alert_service import MonitoringAlertService


class DummyNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def _news_payload(title: str) -> dict:
    return {
        "event_id": "evt-news-1",
        "source": "coindesk",
        "published_at": datetime.now(timezone.utc),
        "title": title,
        "content": "sample content",
        "lang": "en",
        "url": "https://example.com/news/1",
        "dedup_hash": "hash-1",
    }


def test_handle_news_sends_message():
    notifier = DummyNotifier()
    service = MonitoringAlertService(notifier)  # type: ignore[arg-type]

    out = asyncio.run(service.handle_news(_news_payload("Bitcoin ETF approval drives adoption")))

    assert out == []
    assert len(notifier.messages) == 1
    msg = notifier.messages[0]
    assert msg.startswith("[NEWS] source=coindesk")
    assert "title=Bitcoin ETF approval drives adoption" in msg
    assert "url=https://example.com/news/1" in msg


def test_handle_news_truncates_title():
    notifier = DummyNotifier()
    service = MonitoringAlertService(notifier)  # type: ignore[arg-type]
    long_title = "B" * 220

    asyncio.run(service.handle_news(_news_payload(long_title)))

    title_line = notifier.messages[0].splitlines()[1]
    title_text = title_line.removeprefix("title=")
    assert len(title_text) == 180
    assert title_text.endswith("...")
