from datetime import datetime, timezone
from sqlalchemy import Boolean, Float, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class PaperPortfolio(Base):
    __tablename__ = "paper_portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    peak_equity: Mapped[float] = mapped_column(Float, nullable=False)
    current_exposure: Mapped[float] = mapped_column(Float, default=0.0)
    daily_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)

    user = relationship("User", backref="portfolio")
    open_positions = relationship("PaperPosition", back_populates="portfolio", cascade="all, delete-orphan")
    closed_trades = relationship("PaperTrade", back_populates="portfolio", cascade="all, delete-orphan")


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("paper_portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    strategy: Mapped[str] = mapped_column(String(100), nullable=False)

    portfolio = relationship("PaperPortfolio", back_populates="open_positions")


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("paper_portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    exit_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    strategy: Mapped[str] = mapped_column(String(100), nullable=False)

    portfolio = relationship("PaperPortfolio", back_populates="closed_trades")


class AutomationState(Base):
    __tablename__ = "automation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    symbol: Mapped[str] = mapped_column(String(50), default="BTCUSDT")
    interval: Mapped[str] = mapped_column(String(10), default="1h")
    exchange: Mapped[str] = mapped_column(String(50), default="binance")
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_action: Mapped[str] = mapped_column(String(100), default="IDLE")
    last_reason: Mapped[str] = mapped_column(String(255), default="Bot başlatılmadı.")
    
    # Store last signal / decision as JSON strings if needed
    last_signal_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_risk_decision_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", backref="automation_state")
