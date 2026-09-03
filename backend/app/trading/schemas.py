from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MarketRegime(StrEnum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    UNCERTAIN = "UNCERTAIN"


class SignalSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalFilter(BaseModel):
    key: str
    label: str
    passed: bool
    actual: str
    required: str


class Signal(BaseModel):
    symbol: str = "BTC/USDT"
    side: SignalSide
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float = Field(gt=0.0)
    stop_loss: float = Field(gt=0.0)
    take_profit: float = Field(gt=0.0)
    strategy: str
    market_regime: MarketRegime
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    explanation: str
    indicators: dict[str, float] = Field(default_factory=dict)
    filters: list[SignalFilter] = Field(default_factory=list)


class RiskDecision(BaseModel):
    approved: bool
    reason: str
    position_quantity: float = 0.0
    notional_value: float = 0.0
