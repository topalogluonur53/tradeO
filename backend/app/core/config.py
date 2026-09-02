from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "NEXUS AI TRADER"
    environment: Literal["development", "test", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://nexus:nexus_password@localhost:5432/nexus_ai_trader"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    trading_mode: Literal["paper", "testnet"] = "paper"
    kill_switch_enabled: bool = False
    market_data_base_url: str = "https://data-api.binance.vision"
    market_data_timeout_seconds: float = 10.0
    paper_initial_equity: float = 10_000.0
    paper_trade_interval_seconds: float = 30.0
    paper_default_symbol: str = "BTCUSDT"
    paper_default_interval: str = "1h"

    risk_per_trade: float = 0.005
    max_single_position_pct: float = 0.10
    max_total_exposure_pct: float = 0.30
    max_open_positions: int = 3
    daily_loss_limit_pct: float = 0.02
    max_drawdown_limit_pct: float = 0.08
    min_risk_reward: float = 1.5
    cooldown_after_losses: int = 3

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
