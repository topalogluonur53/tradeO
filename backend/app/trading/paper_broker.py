from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.market_data.schemas import Candle
from app.trading.risk_engine import PortfolioSnapshot, RiskEngine
from app.trading.schemas import RiskDecision, Signal, SignalSide


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol for comparison: ETH-USDT -> ETHUSDT"""
    return symbol.replace("-", "").upper()


class PaperPosition(BaseModel):
    id: str
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    opened_at: datetime
    strategy: str


class PaperTrade(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    opened_at: datetime
    closed_at: datetime
    exit_reason: str
    strategy: str


class PaperPortfolioState(BaseModel):
    cash: float
    equity: float
    peak_equity: float
    current_exposure: float
    open_positions: list[PaperPosition]
    closed_trades: list[PaperTrade]
    daily_pnl: float
    consecutive_losses: int


class TradingCycleResult(BaseModel):
    action: str
    reason: str
    signal: Signal | None = None
    risk_decision: RiskDecision | None = None
    portfolio: PaperPortfolioState


class PaperBroker:
    def __init__(
        self,
        initial_equity: float,
        cash: float | None = None,
        peak_equity: float | None = None,
        open_positions: list[PaperPosition] | None = None,
        closed_trades: list[PaperTrade] | None = None,
        consecutive_losses: int = 0,
        trailing_stop_enabled: bool = False,
        trailing_stop_distance_pct: float = 0.03,
    ) -> None:
        self._lock = RLock()
        self._initial_equity = initial_equity
        self._cash = cash if cash is not None else initial_equity
        self._peak_equity = peak_equity if peak_equity is not None else initial_equity
        self._open_positions: list[PaperPosition] = open_positions or []
        self._closed_trades: list[PaperTrade] = closed_trades or []
        self._consecutive_losses = consecutive_losses
        self._trailing_stop_enabled = trailing_stop_enabled
        self._trailing_stop_distance_pct = trailing_stop_distance_pct

    def reset(self, initial_equity: float | None = None) -> PaperPortfolioState:
        with self._lock:
            self._initial_equity = initial_equity or self._initial_equity
            self._cash = self._initial_equity
            self._peak_equity = self._initial_equity
            self._open_positions = []
            self._closed_trades = []
            self._consecutive_losses = 0
            return self.snapshot()

    def snapshot(
        self,
        mark_price: float | None = None,
        mark_symbol: str | None = None,
    ) -> PaperPortfolioState:
        with self._lock:
            open_positions = [
                self._position_with_mark(position, mark_price, mark_symbol)
                for position in self._open_positions
            ]
            self._open_positions = open_positions
            exposure = sum(position.quantity * position.entry_price for position in open_positions)
            market_value = sum(position.quantity * position.current_price for position in open_positions)
            equity = self._cash + market_value
            self._peak_equity = max(self._peak_equity, equity)
            return PaperPortfolioState(
                cash=self._cash,
                equity=equity,
                peak_equity=self._peak_equity,
                current_exposure=exposure,
                open_positions=list(open_positions),
                closed_trades=list(self._closed_trades[-50:]),
                daily_pnl=sum(trade.realized_pnl for trade in self._closed_trades),
                consecutive_losses=self._consecutive_losses,
            )

    def evaluate_existing_positions(self, candle: Candle) -> list[PaperTrade]:
        closed: list[PaperTrade] = []
        with self._lock:
            remaining: list[PaperPosition] = []
            for position in self._open_positions:
                if normalize_symbol(position.symbol) != normalize_symbol(candle.symbol):
                    remaining.append(position)
                    continue

                if self._trailing_stop_enabled:
                    # Trailing Stop Logic: 
                    # Stop is updated if (current high - trailing distance) > current stop
                    potential_new_stop = candle.high * (1.0 - self._trailing_stop_distance_pct)
                    if potential_new_stop > position.stop_loss:
                        position.stop_loss = potential_new_stop

                exit_price: float | None = None
                exit_reason: str | None = None

                if candle.low <= position.stop_loss:
                    exit_price = position.stop_loss
                    exit_reason = "STOP_LOSS"
                elif candle.high >= position.take_profit:
                    exit_price = position.take_profit
                    exit_reason = "TAKE_PROFIT"

                if exit_price is None or exit_reason is None:
                    remaining.append(position)
                    continue

                realized_pnl = (exit_price - position.entry_price) * position.quantity
                self._cash += position.quantity * exit_price
                self._consecutive_losses = self._consecutive_losses + 1 if realized_pnl < 0 else 0
                trade = PaperTrade(
                    id=str(uuid4()),
                    symbol=position.symbol,
                    side="LONG",
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    realized_pnl=realized_pnl,
                    opened_at=position.opened_at,
                    closed_at=datetime.now(UTC),
                    exit_reason=exit_reason,
                    strategy=position.strategy,
                )
                self._closed_trades.append(trade)
                closed.append(trade)

            self._open_positions = remaining
        return closed

    def try_open_position(
        self,
        signal: Signal,
        risk_decision: RiskDecision,
    ) -> str:
        if signal.side is not SignalSide.BUY or not risk_decision.approved:
            return "NO_POSITION_OPENED"

        with self._lock:
            required_cash = risk_decision.notional_value
            if required_cash <= 0 or required_cash > self._cash:
                return "INSUFFICIENT_PAPER_CASH"

            position = PaperPosition(
                id=str(uuid4()),
                symbol=signal.symbol,
                quantity=risk_decision.position_quantity,
                entry_price=signal.entry_price,
                current_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                opened_at=datetime.now(UTC),
                strategy=signal.strategy,
            )
            self._cash -= required_cash
            self._open_positions.append(position)
            return "PAPER_POSITION_OPENED"

    def has_open_position(self, symbol: str) -> bool:
        with self._lock:
            normalized = normalize_symbol(symbol)
            return any(normalize_symbol(position.symbol) == normalized for position in self._open_positions)

    def _position_with_mark(
        self,
        position: PaperPosition,
        mark_price: float | None,
        mark_symbol: str | None,
    ) -> PaperPosition:
        if mark_price is None or mark_symbol != position.symbol:
            current_price = position.current_price
        else:
            current_price = mark_price

        unrealized_pnl = (current_price - position.entry_price) * position.quantity
        notional_value = position.entry_price * position.quantity
        unrealized_pnl_pct = 0.0 if notional_value <= 0 else unrealized_pnl / notional_value
        return position.model_copy(
            update={
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
            }
        )

    def portfolio_snapshot_for_risk(
        self,
        settings: Settings,
        mark_price: float,
        mark_symbol: str | None = None,
    ) -> PortfolioSnapshot:
        state = self.snapshot(mark_price=mark_price, mark_symbol=mark_symbol)
        return PortfolioSnapshot(
            account_equity=state.equity,
            current_exposure=state.current_exposure,
            open_positions=len(state.open_positions),
            daily_pnl=state.daily_pnl,
            peak_equity=state.peak_equity,
            consecutive_losses=state.consecutive_losses,
        )


def create_default_broker(settings: Settings) -> PaperBroker:
    return PaperBroker(initial_equity=settings.paper_initial_equity)
