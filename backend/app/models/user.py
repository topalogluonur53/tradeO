from typing import Any

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
    
    # Automation status
    is_automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trading_mode: Mapped[str] = mapped_column(String(50), default="paper")
