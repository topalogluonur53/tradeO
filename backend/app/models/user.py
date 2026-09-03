from typing import Any

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # User specific API keys
    binance_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    binance_api_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # User specific Risk Limits
    risk_per_trade: Mapped[float] = mapped_column(Float, default=0.005)
    max_single_position_pct: Mapped[float] = mapped_column(Float, default=0.10)
    max_total_exposure_pct: Mapped[float] = mapped_column(Float, default=0.30)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=3)
    daily_loss_limit_pct: Mapped[float] = mapped_column(Float, default=0.02)
    max_drawdown_limit_pct: Mapped[float] = mapped_column(Float, default=0.08)
    min_risk_reward: Mapped[float] = mapped_column(Float, default=1.5)
    cooldown_after_losses: Mapped[int] = mapped_column(Integer, default=3)
    
    # User specific Strategy Configuration
    strategy_bollinger_width: Mapped[float] = mapped_column(Float, default=0.15)
    strategy_rsi_min: Mapped[float] = mapped_column(Float, default=25.0)
    strategy_rsi_max: Mapped[float] = mapped_column(Float, default=78.0)
    strategy_volume_multiplier: Mapped[float] = mapped_column(Float, default=0.3)
    
    # Advanced Strategy Features
    strategy_macd_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy_stoch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mtf_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_stop_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_stop_distance_pct: Mapped[float] = mapped_column(Float, default=0.03)
    
    # Automation status
    is_automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trading_mode: Mapped[str] = mapped_column(String(50), default="paper")
    trading_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    halt_reason: Mapped[str | None] = mapped_column(String(255), default="PAPER_MODE_READY")
