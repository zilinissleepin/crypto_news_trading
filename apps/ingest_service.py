from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from common_types import AppSettings, NewsEvent, Streams
from common_types.bus import EventBus
from feature_store import DedupStore

logger = logging.getLogger(__name__)


DEFAULT_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
}


class IngestService:
    def __init__(self, settings: AppSettings, bus: EventBus, dedup: DedupStore):
        self.settings = settings
        self.bus = bus
        self.dedup = dedup
        self.feeds = DEFAULT_FEEDS

    def _make_dedup_hash(self, source: str, title: str, url: str) -> str:
        raw = f"{source}|{title.strip().lower()}|{url.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _fetch_feed(self, name: str, url: str) -> list[NewsEvent]:
        out: list[NewsEvent] = []
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
        except Exception:
            logger.exception("failed to fetch feed=%s url=%s", name, url)
            return out

        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            content = (entry.get("summary") or title).strip()
            link = (entry.get("link") or "").strip()

            dedup_hash = self._make_dedup_hash(name, title, link)
            seen = await self.dedup.seen_or_add(dedup_hash, ttl_sec=self.settings.default_event_ttl_sec)
            if seen:
                continue

            published = datetime.now(timezone.utc)
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            out.append(
                NewsEvent(
                    event_id=dedup_hash[:16],
                    source=name,
                    published_at=published,
                    title=title,
                    content=content,
                    lang="en",
                    url=link,
                    dedup_hash=dedup_hash,
                )
            )
        return out

    async def run_once(self) -> int:
        total = 0
        for source, url in self.feeds.items():
            events = await self._fetch_feed(source, url)
            for event in events:
                await self.bus.publish(Streams.NEWS_RAW, event.model_dump(mode="json"))
                total += 1
        logger.info("ingest published=%s", total)
        return total

    async def run_forever(self, interval_sec: int = 30) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(interval_sec)
