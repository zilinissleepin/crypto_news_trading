from __future__ import annotations

import os
from functools import cached_property

from pydantic import Field


try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class AppSettings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

        env: str = "dev"
        log_level: str = "INFO"

        redis_url: str = "redis://localhost:6379/0"
        postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/crypto_trading"
        bus_backend: str = "redis"

        openai_api_key: str = ""
        openai_model: str = "qwen-plus"
        openai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        telegram_bot_token: str = ""
        telegram_chat_id: str = ""

        binance_api_key: str = ""
        binance_api_secret: str = ""
        binance_use_testnet: bool = True
        binance_recv_window_ms: int = 5000

        account_equity_usd: float = 100000.0
        risk_per_trade_pct: float = 0.005
        max_symbol_exposure_pct: float = 0.05
        max_total_exposure_pct: float = 0.20
        max_spot_exposure_pct: float = 0.12
        max_perp_exposure_pct: float = 0.12
        max_long_exposure_pct: float = 0.12
        max_short_exposure_pct: float = 0.12
        max_daily_drawdown_pct: float = 0.02
        min_signal_confidence: float = 0.65
        default_event_ttl_sec: int = 3600
        max_slippage_bps: int = 20

        execution_mode: str = "paper"
        universe_symbols: str = Field(default="BTCUSDT,ETHUSDT")

        service_poll_ms: int = 1500
        service_idle_sleep_sec: float = 0.2
        position_sync_interval_sec: int = 30
        position_sync_drift_alert_pct: float = 0.02

        @cached_property
        def universe(self) -> set[str]:
            return {s.strip().upper() for s in self.universe_symbols.split(",") if s.strip()}
except ModuleNotFoundError:
    from pydantic import BaseModel

    class AppSettings(BaseModel):
        env: str = Field(default_factory=lambda: os.getenv("ENV", "dev"))
        log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

        redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        postgres_dsn: str = Field(
            default_factory=lambda: os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/crypto_trading")
        )
        bus_backend: str = Field(default_factory=lambda: os.getenv("BUS_BACKEND", "redis"))

        openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
        openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "qwen-plus"))
        openai_base_url: str = Field(
            default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        )

        telegram_bot_token: str = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
        telegram_chat_id: str = Field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

        binance_api_key: str = Field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
        binance_api_secret: str = Field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
        binance_use_testnet: bool = Field(
            default_factory=lambda: os.getenv("BINANCE_USE_TESTNET", "true").strip().lower() in {"1", "true", "yes", "on"}
        )
        binance_recv_window_ms: int = Field(default_factory=lambda: int(os.getenv("BINANCE_RECV_WINDOW_MS", "5000")))

        account_equity_usd: float = Field(default_factory=lambda: float(os.getenv("ACCOUNT_EQUITY_USD", "100000")))
        risk_per_trade_pct: float = Field(default_factory=lambda: float(os.getenv("RISK_PER_TRADE_PCT", "0.005")))
        max_symbol_exposure_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_SYMBOL_EXPOSURE_PCT", "0.05")))
        max_total_exposure_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.2")))
        max_spot_exposure_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_SPOT_EXPOSURE_PCT", "0.12")))
        max_perp_exposure_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_PERP_EXPOSURE_PCT", "0.12")))
        max_long_exposure_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_LONG_EXPOSURE_PCT", "0.12")))
        max_short_exposure_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_SHORT_EXPOSURE_PCT", "0.12")))
        max_daily_drawdown_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.02")))
        min_signal_confidence: float = Field(default_factory=lambda: float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.65")))
        default_event_ttl_sec: int = Field(default_factory=lambda: int(os.getenv("DEFAULT_EVENT_TTL_SEC", "3600")))
        max_slippage_bps: int = Field(default_factory=lambda: int(os.getenv("MAX_SLIPPAGE_BPS", "20")))

        execution_mode: str = Field(default_factory=lambda: os.getenv("EXECUTION_MODE", "paper"))
        universe_symbols: str = Field(default_factory=lambda: os.getenv("UNIVERSE_SYMBOLS", "BTCUSDT,ETHUSDT"))

        service_poll_ms: int = Field(default_factory=lambda: int(os.getenv("SERVICE_POLL_MS", "1500")))
        service_idle_sleep_sec: float = Field(default_factory=lambda: float(os.getenv("SERVICE_IDLE_SLEEP_SEC", "0.2")))
        position_sync_interval_sec: int = Field(default_factory=lambda: int(os.getenv("POSITION_SYNC_INTERVAL_SEC", "30")))
        position_sync_drift_alert_pct: float = Field(
            default_factory=lambda: float(os.getenv("POSITION_SYNC_DRIFT_ALERT_PCT", "0.02"))
        )

        @cached_property
        def universe(self) -> set[str]:
            return {s.strip().upper() for s in self.universe_symbols.split(",") if s.strip()}
