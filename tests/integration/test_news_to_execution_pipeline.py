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


def test_news_raw_to_execution_report_end_to_end():
    settings = AppSettings(
        bus_backend="memory",
        universe_symbols="BTCUSDT,ETHUSDT",
        min_signal_confidence=0.6,
    )

    entity = EntityService(settings)
    llm = LLMSignalService(settings, LLMProvider(settings))
    fusion = SignalFusionService(settings)
    universe = UniverseService(settings)
    portfolio = PortfolioService(settings)
    risk = RiskService(settings, MemoryTradingStateStore())
    execution = ExecutionService(SimulatedExchangeAdapter())
    pnl = PositionPnLService()

    news = {
        "event_id": "evt-1",
        "source": "test",
        "published_at": datetime.now(timezone.utc),
        "title": "Bitcoin partnership drives adoption",
        "content": "Major partnership expected to increase bitcoin adoption and inflow.",
        "lang": "en",
        "url": "https://example.com",
        "dedup_hash": "abc123",
    }

    e_out = asyncio.run(entity.handle(news))
    assert e_out

    _, entity_payload = e_out[0]
    s_out = asyncio.run(llm.handle(entity_payload))
    assert s_out

    _, raw_signal_payload = s_out[0]
    f_out = asyncio.run(fusion.handle(raw_signal_payload))
    assert f_out

    _, tradeable_payload = f_out[0]
    u_out = asyncio.run(universe.handle(tradeable_payload))
    assert u_out

    _, uni_payload = u_out[0]
    p_out = asyncio.run(portfolio.handle(uni_payload))
    assert p_out

    _, intent_payload = p_out[0]
    r_out = asyncio.run(risk.handle_order_intent(intent_payload))
    assert r_out

    stream, approved_payload = r_out[0]
    assert stream == "order.approved"

    x_out = asyncio.run(execution.handle(approved_payload))
    assert x_out

    _, exec_payload = x_out[0]
    pnl_out = asyncio.run(pnl.handle(exec_payload))
    assert pnl_out
