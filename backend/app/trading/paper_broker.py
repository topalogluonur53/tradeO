from datetime import UTC, datetime
import math
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
    entry_fee: float = 0.0
    initial_stop_loss: float = 0.0
    highest_price: float = 0.0
    bars_held: int = 0
    last_counted_close_time: int = 0
    entry_candle_close_time: int = 0
    stop_type: str = "INITIAL"


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
    fees_paid: float = 0.0


class PaperPortfolioState(BaseModel):
    initial_equity: float = 10_000.0
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
        trailing_stop_activation_r: float = 1.5,
        breakeven_stop_enabled: bool = True,
        breakeven_trigger_r: float = 1.0,
        time_stop_enabled: bool = True,
        max_holding_bars: int = 48,
        fee_rate: float = 0.0,
        slippage_bps: float = 0.0,
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
        self._trailing_stop_activation_r = max(0.0, trailing_stop_activation_r)
        self._breakeven_stop_enabled = breakeven_stop_enabled
        self._breakeven_trigger_r = max(0.0, breakeven_trigger_r)
        self._time_stop_enabled = time_stop_enabled
        self._max_holding_bars = max(1, max_holding_bars)
        self._fee_rate = max(0.0, fee_rate)
        self._slippage_rate = max(0.0, slippage_bps) / 10_000.0

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
        mark_prices: dict[str, float] | None = None,
    ) -> PaperPortfolioState:
        with self._lock:
            open_positions = [
                self._position_with_mark(position, mark_price, mark_symbol, mark_prices)
                for position in self._open_positions
            ]
            self._open_positions = open_positions
            exposure = sum(
                (position.quantity * position.entry_price) + position.entry_fee
                for position in open_positions
            )
            market_value = sum(position.quantity * position.current_price for position in open_positions)
            estimated_exit_fees = market_value * self._fee_rate
            equity = self._cash + market_value - estimated_exit_fees
            self._peak_equity = max(self._peak_equity, equity)
            return PaperPortfolioState(
                initial_equity=self._initial_equity,
                cash=self._cash,
                equity=equity,
                peak_equity=self._peak_equity,
                current_exposure=exposure,
                open_positions=list(open_positions),
                closed_trades=list(self._closed_trades[-50:]),
                daily_pnl=sum(
                    trade.realized_pnl
                    for trade in self._closed_trades
                    if _as_utc(trade.closed_at).date() == datetime.now(UTC).date()
                ),
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

                exit_price: float | None = None
                exit_reason: str | None = None

                # The running candle contains extrema from before a position
                # may have opened. During that entry candle, only the latest
                # observed price is safe to use for protective exits.
                is_entry_candle = (
                    position.entry_candle_close_time > 0
                    and candle.close_time <= position.entry_candle_close_time
                )
                observed_low = candle.close if is_entry_candle else candle.low
                observed_high = candle.close if is_entry_candle else candle.high
                is_new_candle = candle.close_time > position.last_counted_close_time
                if is_new_candle and not is_entry_candle:
                    position.bars_held += 1
                    position.last_counted_close_time = candle.close_time

                # A stop-market cannot fill at the requested stop after a gap
                # through it. Model the worse candle-open fill, then apply the
                # configured sell slippage and fee in _create_trade_from_position.
                if not is_entry_candle and candle.open <= position.stop_loss:
                    exit_price = candle.open
                    exit_reason = "STOP_LOSS_GAP"
                elif observed_low <= position.stop_loss:
                    exit_price = min(position.stop_loss, candle.close) if is_entry_candle else position.stop_loss
                    exit_reason = self._stop_exit_reason(position.stop_type)
                elif not is_entry_candle and candle.open >= position.take_profit:
                    exit_price = position.take_profit
                    exit_reason = "TAKE_PROFIT"
                elif observed_high >= position.take_profit:
                    exit_price = position.take_profit
                    exit_reason = "TAKE_PROFIT"
                elif (
                    self._time_stop_enabled
                    and is_new_candle
                    and position.bars_held >= self._max_holding_bars
                ):
                    exit_price = candle.close
                    exit_reason = "TIME_STOP"

                if exit_price is None or exit_reason is None:
                    self._update_protective_stop(position, observed_high)
                    remaining.append(position)
                    continue

                trade = self._create_trade_from_position(
                    position,
                    exit_price,
                    exit_reason,
                    closed_at=min(
                        datetime.fromtimestamp(candle.close_time / 1000, tz=UTC),
                        datetime.now(UTC),
                    ),
                )
                closed.append(trade)

            self._open_positions = remaining
        return closed

    def _update_protective_stop(
        self,
        position: PaperPosition,
        observed_high: float,
    ) -> None:
        """Tighten protection after evaluating the candle; never loosen it."""
        position.highest_price = max(
            position.highest_price or position.entry_price,
            observed_high,
        )
        initial_stop = position.initial_stop_loss or position.stop_loss
        initial_risk = position.entry_price - initial_stop
        if initial_risk <= 0:
            return

        profit_in_r = (position.highest_price - position.entry_price) / initial_risk
        next_stop = position.stop_loss
        next_type = position.stop_type

        if self._breakeven_stop_enabled and profit_in_r >= self._breakeven_trigger_r:
            breakeven_stop = self._breakeven_stop_price(position)
            if breakeven_stop > next_stop:
                next_stop = breakeven_stop
                next_type = "BREAK_EVEN"

        if self._trailing_stop_enabled and profit_in_r >= self._trailing_stop_activation_r:
            trailing_stop = position.highest_price * (1.0 - self._trailing_stop_distance_pct)
            if trailing_stop > next_stop:
                next_stop = trailing_stop
                next_type = "TRAILING"

        # Protective stops must remain below the profit target. This also
        # guards malformed configuration from turning a stop into a limit exit.
        position.stop_loss = min(next_stop, position.take_profit * (1.0 - 1e-9))
        position.stop_type = next_type

    def _breakeven_stop_price(self, position: PaperPosition) -> float:
        """Raw stop price whose simulated net proceeds cover entry costs."""
        per_unit_entry_cost = position.entry_price
        if position.quantity > 0:
            per_unit_entry_cost += position.entry_fee / position.quantity
        net_exit_factor = (1.0 - self._slippage_rate) * (1.0 - self._fee_rate)
        if net_exit_factor <= 0:
            return position.entry_price
        return per_unit_entry_cost / net_exit_factor

    @staticmethod
    def _stop_exit_reason(stop_type: str) -> str:
        if stop_type == "TRAILING":
            return "TRAILING_STOP"
        if stop_type == "BREAK_EVEN":
            return "BREAK_EVEN_STOP"
        return "STOP_LOSS"

    def close_position(self, position_id: str) -> PaperTrade | None:
        with self._lock:
            for i, position in enumerate(self._open_positions):
                if position.id == position_id:
                    trade = self._create_trade_from_position(position, exit_price=position.current_price, exit_reason="MANUAL_CLOSE")
                    self._open_positions.pop(i)
                    return trade
        return None

    def close_all_positions(self) -> list[PaperTrade]:
        with self._lock:
            closed_trades = []
            for position in self._open_positions:
                trade = self._create_trade_from_position(position, exit_price=position.current_price, exit_reason="MANUAL_CLOSE")
                closed_trades.append(trade)
            self._open_positions = []
            return closed_trades

    def close_symbol(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str = "STRATEGY_EXIT",
    ) -> PaperTrade | None:
        with self._lock:
            exact_symbol = symbol.upper().strip()
            for index, position in enumerate(self._open_positions):
                if position.symbol.upper().strip() == exact_symbol:
                    trade = self._create_trade_from_position(
                        position,
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                    )
                    self._open_positions.pop(index)
                    return trade
        return None

    def _create_trade_from_position(
        self,
        position: PaperPosition,
        exit_price: float,
        exit_reason: str,
        closed_at: datetime | None = None,
    ) -> PaperTrade:
        execution_price = exit_price * (1.0 - self._slippage_rate)
        exit_notional = position.quantity * execution_price
        exit_fee = exit_notional * self._fee_rate
        realized_pnl = (
            (execution_price - position.entry_price) * position.quantity
            - position.entry_fee
            - exit_fee
        )
        self._cash += exit_notional - exit_fee
        self._consecutive_losses = self._consecutive_losses + 1 if realized_pnl < 0 else 0
        trade = PaperTrade(
            id=str(uuid4()),
            symbol=position.symbol,
            side="LONG",
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=execution_price,
            realized_pnl=realized_pnl,
            opened_at=position.opened_at,
            closed_at=closed_at or datetime.now(UTC),
            exit_reason=exit_reason,
            strategy=position.strategy,
            fees_paid=position.entry_fee + exit_fee,
        )
        self._closed_trades.append(trade)
        return trade

    def try_open_position(
        self,
        signal: Signal,
        risk_decision: RiskDecision,
        entry_candle_close_time: int = 0,
    ) -> str:
        if signal.side is not SignalSide.BUY or not risk_decision.approved:
            return "NO_POSITION_OPENED"

        with self._lock:
            execution_price = signal.entry_price * (1.0 + self._slippage_rate)
            notional_value = risk_decision.position_quantity * execution_price
            entry_fee = notional_value * self._fee_rate
            required_cash = notional_value + entry_fee
            if required_cash <= 0 or (
                required_cash > self._cash
                and not math.isclose(required_cash, self._cash, rel_tol=1e-12)
            ):
                return "INSUFFICIENT_PAPER_CASH"

            position = PaperPosition(
                id=str(uuid4()),
                symbol=signal.symbol,
                quantity=risk_decision.position_quantity,
                entry_price=execution_price,
                current_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                opened_at=datetime.now(UTC),
                strategy=signal.strategy,
                entry_fee=entry_fee,
                initial_stop_loss=signal.stop_loss,
                highest_price=execution_price,
                entry_candle_close_time=entry_candle_close_time,
                last_counted_close_time=entry_candle_close_time,
            )
            self._cash = max(0.0, self._cash - required_cash)
            self._open_positions.append(position)
            return "PAPER_POSITION_OPENED"

    def has_open_position(self, symbol: str) -> bool:
        with self._lock:
            normalized = normalize_symbol(symbol)
            return any(normalize_symbol(position.symbol) == normalized for position in self._open_positions)

    def has_exact_open_position(self, symbol: str) -> bool:
        """Match an exchange-specific symbol without merging BTCUSDT/BTC-USDT."""
        with self._lock:
            normalized = symbol.upper().strip()
            return any(position.symbol.upper().strip() == normalized for position in self._open_positions)

    def has_closed_at_or_after(self, symbol: str, signal_time: datetime) -> bool:
        """Prevent re-entry from a candle that already produced an exit."""
        with self._lock:
            normalized = normalize_symbol(symbol)
            comparable_signal_time = _as_utc(signal_time)
            return any(
                normalize_symbol(trade.symbol) == normalized
                and _as_utc(trade.closed_at) >= comparable_signal_time
                for trade in self._closed_trades
            )

    def _position_with_mark(
        self,
        position: PaperPosition,
        mark_price: float | None,
        mark_symbol: str | None,
        mark_prices: dict[str, float] | None = None,
    ) -> PaperPosition:
        normalized_symbol = normalize_symbol(position.symbol)
        ticker_price = None
        if mark_prices:
            ticker_price = mark_prices.get(position.symbol.upper().strip())
            if ticker_price is None:
                ticker_price = mark_prices.get(normalized_symbol)
        if ticker_price is not None and ticker_price > 0:
            current_price = ticker_price
        elif mark_price is None or normalize_symbol(mark_symbol or "") != normalized_symbol:
            current_price = position.current_price
        else:
            current_price = mark_price

        estimated_exit_fee = current_price * position.quantity * self._fee_rate
        unrealized_pnl = (
            (current_price - position.entry_price) * position.quantity
            - position.entry_fee
            - estimated_exit_fee
        )
        notional_value = (position.entry_price * position.quantity) + position.entry_fee
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
        max_total_exposure_value: float | None = None,
        max_position_value: float | None = None,
    ) -> PortfolioSnapshot:
        state = self.snapshot(mark_price=mark_price, mark_symbol=mark_symbol)
        return PortfolioSnapshot(
            account_equity=state.equity,
            current_exposure=state.current_exposure,
            open_positions=len(state.open_positions),
            daily_pnl=state.daily_pnl,
            peak_equity=state.peak_equity,
            consecutive_losses=state.consecutive_losses,
            available_cash=state.cash,
            max_total_exposure_value=max_total_exposure_value,
            max_position_value=max_position_value,
        )


def create_default_broker(settings: Settings) -> PaperBroker:
    return PaperBroker(
        initial_equity=settings.paper_initial_equity,
        fee_rate=settings.paper_fee_rate,
        slippage_bps=settings.paper_slippage_bps,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
