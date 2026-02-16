from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apps.entity_service import EntityService
from apps.execution_service import ExecutionService
from apps.llm_signal_service import LLMProvider, LLMSignalService
from apps.portfolio_service import PortfolioService
from apps.position_pnl_service import PositionPnLService
from apps.risk_service import RiskService
from apps.signal_fusion_service import SignalFusionService
from apps.universe_service import UniverseService
from common_types import AppSettings
from exchange_adapters import SimulatedExchangeAdapter
from feature_store import MemoryTradingStateStore


async def main() -> None:
    settings = AppSettings(bus_backend="memory", universe_symbols="BTCUSDT,ETHUSDT")

    entity = EntityService(settings)
    llm = LLMSignalService(settings, LLMProvider(settings))
    fusion = SignalFusionService(settings)
    universe = UniverseService(settings)
    portfolio = PortfolioService(settings)
    risk = RiskService(settings, MemoryTradingStateStore())
    execution = ExecutionService(SimulatedExchangeAdapter())
    pnl = PositionPnLService()

    news = {
        "event_id": "demo-event-1",
        "source": "demo",
        "published_at": datetime.now(timezone.utc),
        "title": "Bitcoin partnership drives strong adoption",
        "content": "A major partnership is expected to drive inflow and adoption for bitcoin.",
        "lang": "en",
        "url": "https://example.com/news/1",
        "dedup_hash": "demo-hash-1",
    }

    e = await entity.handle(news)
    _, entity_payload = e[0]

    s = await llm.handle(entity_payload)
    _, signal_payload = s[0]

    f = await fusion.handle(signal_payload)
    _, tradeable_payload = f[0]

    u = await universe.handle(tradeable_payload)
    _, universe_payload = u[0]

    p = await portfolio.handle(universe_payload)
    _, intent_payload = p[0]

    r = await risk.handle_order_intent(intent_payload)
    stream, approved_or_rejected = r[0]

    print("RISK:", stream, approved_or_rejected)
    if stream != "order.approved":
        return

    x = await execution.handle(approved_or_rejected)
    _, report = x[0]
    print("EXEC:", report)

    snaps = await pnl.handle(report)
    _, snapshot = snaps[0]
    print("PNL:", snapshot)


if __name__ == "__main__":
    asyncio.run(main())
