from __future__ import annotations

import logging
import re

from common_types import AppSettings, EntityEvent, NewsEvent, Streams

logger = logging.getLogger(__name__)

SYMBOL_ALIASES = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "bnb": "BNBUSDT",
    "solana": "SOLUSDT",
    "xrp": "XRPUSDT",
    "cardano": "ADAUSDT",
    "dogecoin": "DOGEUSDT",
    "chainlink": "LINKUSDT",
    "avalanche": "AVAXUSDT",
    "toncoin": "TONUSDT",
}

TAG_KEYWORDS = {
    "etf": "macro",
    "hack": "security",
    "exploit": "security",
    "partnership": "adoption",
    "listing": "exchange",
    "delist": "exchange",
    "regulation": "regulation",
    "sec": "regulation",
}


class EntityService:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def extract_symbols(self, text: str) -> list[str]:
        symbols: set[str] = set()

        upper_text = text.upper()
        for symbol in self.settings.universe:
            if symbol in upper_text:
                symbols.add(symbol)

        lower_text = text.lower()
        for alias, symbol in SYMBOL_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", lower_text):
                symbols.add(symbol)

        return sorted(symbols)

    def extract_tags(self, text: str) -> list[str]:
        lower_text = text.lower()
        tags = {tag for keyword, tag in TAG_KEYWORDS.items() if keyword in lower_text}
        return sorted(tags)

    async def handle(self, payload: dict) -> list[tuple[str, dict]]:
        news = NewsEvent.model_validate(payload)
        merged_text = f"{news.title}\n{news.content}"
        symbols = self.extract_symbols(merged_text)
        tags = self.extract_tags(merged_text)

        if not symbols:
            logger.debug("entity no symbols event_id=%s", news.event_id)
            return []

        entity = EntityEvent(
            event_id=news.event_id,
            symbols=symbols,
            tags=tags,
            regions=[],
            relevance_score=min(1.0, 0.5 + 0.1 * len(tags) + 0.1 * len(symbols)),
            title=news.title,
            content=news.content,
        )
        return [(Streams.NEWS_ENTITY, entity.model_dump(mode="json"))]
