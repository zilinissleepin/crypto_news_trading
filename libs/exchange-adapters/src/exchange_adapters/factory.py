from __future__ import annotations

from common_types.config import AppSettings

from .base import ExchangeAdapter
from .binance import BinanceExchangeAdapter
from .simulated import SimulatedExchangeAdapter


def build_exchange_adapter(settings: AppSettings) -> ExchangeAdapter:
    if settings.execution_mode.lower() == "paper":
        return SimulatedExchangeAdapter()
    return BinanceExchangeAdapter(
        settings.binance_api_key,
        settings.binance_api_secret,
        use_testnet=settings.binance_use_testnet,
        recv_window_ms=settings.binance_recv_window_ms,
    )
