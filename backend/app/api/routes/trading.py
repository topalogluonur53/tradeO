from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.models.trading import AutomationState as DBAutomationState
from app.market_data.binance import BinanceMarketDataClient, MarketDataError, normalize_exchange
from app.market_data.offline import build_offline_candles
from app.market_data.okx import OkxMarketDataClient
from app.trading.paper_broker import PaperPortfolioState, TradingCycleResult, PaperPosition, PaperTrade
from app.trading.paper_trading import ActivationValidationSummary, AutomationState, PaperTradingService
from app.trading.multi_tenant import execute_trading_step_for_user, get_or_create_automation_state, get_or_create_portfolio, close_position_for_user, close_all_positions_for_user
from app.trading.schemas import SignalSide, Signal, RiskDecision
from app.trading.strategy_engine import NexusAIStrategy

router = APIRouter(prefix="/trading", tags=["trading"])


class TradingStateResponse(BaseModel):
    automation: AutomationState
    portfolio: PaperPortfolioState


class BacktestSummary(BaseModel):
    symbol: str
    interval: str
    candles: int
    initial_equity: float
    signals: int
    wins: int
    losses: int
    net_pnl: float
    ending_equity: float
    return_pct: float
    max_drawdown_pct: float
    open_position_pnl: float
    period_start: datetime | None
    period_end: datetime | None
    data_source: str
    fees_paid: float = 0.0


class ResetPaperPortfolioRequest(BaseModel):
    initial_equity: float | None = Field(default=None, gt=0.0, le=1_000_000_000.0)


def parse_stored_model(raw_value: str | None, model_type: type[Signal] | type[RiskDecision]):
    if not raw_value:
        return None
    try:
        return model_type.model_validate_json(raw_value)
    except (ValueError, TypeError):
        # Historical data must not make the entire paper-trading screen fail.
        return None


def normalize_trading_exchange(exchange: str) -> str:
    selected_exchange = normalize_exchange(exchange)
    if selected_exchange not in {"binance", "okx", "all"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exchange must be one of: binance, okx, all",
        )
    return selected_exchange


@router.get("/state", response_model=TradingStateResponse)
def trading_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TradingStateResponse:
    auto_state = get_or_create_automation_state(db, current_user)
    portfolio = get_or_create_portfolio(db, current_user)
    
    # Parse last signal and risk decision
    last_signal = None
    last_signal = parse_stored_model(auto_state.last_signal_json, Signal)
        
    last_risk = None
    last_risk = parse_stored_model(auto_state.last_risk_decision_json, RiskDecision)
    
    return TradingStateResponse(
        automation=AutomationState(
            enabled=auto_state.enabled,
            running=auto_state.running,
            symbol=auto_state.symbol,
            interval=auto_state.interval,
            exchange=auto_state.exchange,
            position_count=auto_state.position_count,
            allocation_usd=auto_state.allocation_usd or portfolio.equity,
            allocation_per_position_usd=(auto_state.allocation_usd or portfolio.equity) / max(auto_state.position_count, 1),
            last_cycle_at=auto_state.last_cycle_at,
            last_action=auto_state.last_action,
            last_reason=auto_state.last_reason,
            last_signal=last_signal,
            last_risk_decision=last_risk
        ),
        portfolio=PaperPortfolioState(
            initial_equity=portfolio.initial_equity,
            cash=portfolio.cash,
            equity=portfolio.equity,
            peak_equity=portfolio.peak_equity,
            current_exposure=portfolio.current_exposure,
            open_positions=[
                PaperPosition(
                    id=p.id,
                    symbol=p.symbol,
                    quantity=p.quantity,
                    entry_price=p.entry_price,
                    current_price=p.current_price,
                    stop_loss=p.stop_loss,
                    take_profit=p.take_profit,
                    unrealized_pnl=p.unrealized_pnl,
                    unrealized_pnl_pct=p.unrealized_pnl_pct,
                    opened_at=p.opened_at,
                    strategy=p.strategy,
                    entry_fee=p.entry_fee,
                ) for p in portfolio.open_positions
            ],
            closed_trades=[
                PaperTrade(
                    id=t.id,
                    symbol=t.symbol,
                    side=t.side,
                    quantity=t.quantity,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    realized_pnl=t.realized_pnl,
                    opened_at=t.opened_at,
                    closed_at=t.closed_at,
                    exit_reason=t.exit_reason,
                    strategy=t.strategy,
                    fees_paid=t.fees_paid,
                ) for t in portfolio.closed_trades[-50:]
            ],
            daily_pnl=portfolio.daily_pnl,
            consecutive_losses=portfolio.consecutive_losses
        ),
    )


@router.get("/validation", response_model=ActivationValidationSummary)
async def activation_validation(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    exchange: str = Query(default="binance", min_length=2, max_length=12),
    position_count: int = Query(default=3, ge=1, le=50),
    allocation_usd: float | None = Query(default=None, gt=0.0, le=1_000_000_000.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ActivationValidationSummary:
    try:
        selected_exchange = normalize_trading_exchange(exchange)
        service = PaperTradingService(get_settings())
        return await service.validate_activation(
            symbol=symbol,
            interval=interval,
            exchange=selected_exchange,
            position_count=position_count,
            allocation_usd=allocation_usd,
        )
    except (ValueError, MarketDataError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/step", response_model=TradingCycleResult)
async def run_trading_step(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    exchange: str = Query(default="binance", min_length=2, max_length=12),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TradingCycleResult:
    try:
        selected_exchange = normalize_trading_exchange(exchange)
        return await execute_trading_step_for_user(
            db=db, user=current_user, symbol=symbol, interval=interval, exchange=selected_exchange
        )
    except (ValueError, MarketDataError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/automation/start", response_model=AutomationState)
async def start_automation(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    exchange: str = Query(default="binance", min_length=2, max_length=12),
    position_count: int | None = Query(default=None, ge=1, le=50),
    allocation_usd: float | None = Query(default=None, gt=0.0, le=1_000_000_000.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AutomationState:
    if current_user.trading_halted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Paper trading is halted. Resume paper mode before starting automation.",
        )
    if current_user.trading_mode != "paper":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only paper trading automation is available.",
        )

    selected_exchange = normalize_trading_exchange(exchange)
    auto_state = get_or_create_automation_state(db, current_user)
    portfolio = get_or_create_portfolio(db, current_user)
    selected_position_count = position_count if position_count is not None else auto_state.position_count
    selected_allocation = (
        allocation_usd
        if allocation_usd is not None
        else auto_state.allocation_usd or portfolio.cash
    )
    if selected_allocation > portfolio.equity:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Toplam pozisyon bütçesi mevcut equity değerini aşamaz ({portfolio.equity:.2f} USD).",
        )

    service = PaperTradingService(get_settings())
    validation = await service.validate_activation(
        symbol=symbol,
        interval=interval,
        exchange=selected_exchange,
        position_count=selected_position_count,
        allocation_usd=selected_allocation,
    )
    if not validation.ready:
        failed = ", ".join(row.name for row in validation.rows if not row.passed)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Activation validation failed: {failed}",
        )
    
    # Persist the selected settings before the initial cycle, but do not make
    # them visible to the worker yet. This prevents the API's first cycle and
    # the worker's first cycle from trading the same portfolio concurrently.
    auto_state.enabled = False
    auto_state.running = False
    auto_state.symbol = symbol
    auto_state.interval = interval
    auto_state.exchange = selected_exchange
    auto_state.position_count = selected_position_count
    auto_state.allocation_usd = selected_allocation
    auto_state.last_action = "AUTO_STARTING"
    auto_state.last_reason = "Preparing the first paper automation cycle"
    db.commit()

    # Run the first selected-market cycle immediately. The standalone worker keeps
    # scanning afterwards, but the user should not have to wait for its next
    # 30-second interval to see the bot react.
    try:
        await execute_trading_step_for_user(
            db=db,
            user=current_user,
            symbol=symbol,
            interval=interval,
            exchange=selected_exchange,
        )
    except Exception as exc:
        db.rollback()
        auto_state = db.get(DBAutomationState, auto_state.id)
        if auto_state is None:
            raise
        auto_state.last_action = "AUTO_ERROR"
        auto_state.last_reason = f"Initial paper cycle failed: {exc}"
    else:
        auto_state = db.get(DBAutomationState, auto_state.id)
        if auto_state is None:
            raise RuntimeError("Paper automation state disappeared during startup")

    # Enable only after the synchronous initial step has finished. If that
    # step failed, leave the automation enabled so the resilient worker can
    # retry it on the next interval while exposing AUTO_ERROR to the UI.
    auto_state.enabled = True
    auto_state.running = True
    db.commit()

    
    return trading_state(current_user, db).automation


@router.post("/automation/stop", response_model=AutomationState)
async def stop_automation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AutomationState:
    auto_state = get_or_create_automation_state(db, current_user)
    auto_state.enabled = False
    auto_state.running = False
    auto_state.last_action = "AUTO_STOPPED"
    auto_state.last_reason = "Paper automation loop stopped"
    db.commit()
    return trading_state(current_user, db).automation


@router.post("/positions/{position_id}/close", response_model=TradingCycleResult)
async def close_position_endpoint(
    position_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TradingCycleResult:
    return await close_position_for_user(db, current_user, position_id)


@router.post("/positions/close-all", response_model=TradingCycleResult)
async def close_all_positions_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TradingCycleResult:
    return await close_all_positions_for_user(db, current_user)


@router.post("/reset", response_model=PaperPortfolioState)
def reset_paper_portfolio(
    payload: ResetPaperPortfolioRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PaperPortfolioState:
    settings = get_settings()
    portfolio = get_or_create_portfolio(db, current_user)
    initial_equity = (
        payload.initial_equity
        if payload and payload.initial_equity is not None
        else portfolio.initial_equity or settings.paper_initial_equity
    )
    portfolio.initial_equity = initial_equity
    portfolio.cash = initial_equity
    portfolio.equity = initial_equity
    portfolio.peak_equity = initial_equity
    portfolio.current_exposure = 0.0
    portfolio.daily_pnl = 0.0
    portfolio.consecutive_losses = 0
    
    # Delete open positions and trades
    for pos in portfolio.open_positions:
        db.delete(pos)
    for trade in portfolio.closed_trades:
        db.delete(trade)
        
    db.commit()
    return trading_state(current_user, db).portfolio


@router.get("/backtest", response_model=BacktestSummary)
async def run_backtest(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    limit: int = Query(default=300, ge=60, le=1000),
    exchange: str = Query(default="binance", min_length=2, max_length=12),
    initial_equity: float | None = Query(default=None, gt=0.0, le=1_000_000_000.0),
) -> BacktestSummary:
    settings = get_settings()
    strategy = NexusAIStrategy(mtf_enabled=True)
    selected_exchange = normalize_exchange(exchange)
    if selected_exchange == "all":
        selected_exchange = "binance"

    try:
        if selected_exchange == "okx":
            client = OkxMarketDataClient(timeout_seconds=settings.market_data_timeout_seconds)
            series = await client.get_candles(symbol=symbol, interval=interval, limit=min(limit, 300))
        else:
            client = BinanceMarketDataClient(
                base_url=settings.market_data_base_url,
                timeout_seconds=settings.market_data_timeout_seconds,
            )
            series = await client.get_candles(symbol=symbol, interval=interval, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MarketDataError:
        series = build_offline_candles(
            symbol=symbol,
            interval=interval,
            limit=min(limit, 300) if selected_exchange == "okx" else limit,
            exchange=selected_exchange,
        )

    if "public_market_data" in series.source:
        finalized = [candle for candle in series.candles if candle.is_closed]
        if finalized:
            series = series.model_copy(update={"candles": finalized})

    starting_equity = initial_equity or settings.paper_initial_equity
    equity = starting_equity
    position_entry: float | None = None
    stop_loss = 0.0
    take_profit = 0.0
    quantity = 0.0
    signals = 0
    wins = 0
    losses = 0
    net_pnl = 0.0
    fees_paid = 0.0
    peak_equity = starting_equity
    max_drawdown_pct = 0.0

    for index in range(30, len(series.candles)):
        window = series.candles[: index + 1]
        candle = window[-1]
        signal = strategy.generate_signal(series.symbol, window)

        closed_this_candle = False
        if position_entry is not None:
            exit_price = None
            if candle.low <= stop_loss:
                exit_price = stop_loss
            elif candle.high >= take_profit:
                exit_price = take_profit
            elif signal.side is SignalSide.SELL:
                exit_price = candle.close

            if exit_price is not None:
                execution_exit = exit_price * (1.0 - settings.paper_slippage_bps / 10_000.0)
                exit_fee = execution_exit * quantity * settings.paper_fee_rate
                fees_paid += exit_fee
                realized_pnl = (execution_exit - position_entry) * quantity - exit_fee
                net_pnl += realized_pnl
                equity += realized_pnl
                wins += 1 if realized_pnl > 0 else 0
                losses += 1 if realized_pnl <= 0 else 0
                position_entry = None
                closed_this_candle = True

        if position_entry is None and not closed_this_candle:
            if signal.side is SignalSide.BUY:
                signals += 1
                risk_amount = equity * settings.risk_per_trade
                execution_entry = signal.entry_price * (
                    1.0 + settings.paper_slippage_bps / 10_000.0
                )
                entry_fee_per_unit = execution_entry * settings.paper_fee_rate
                stop_proceeds = signal.stop_loss * (
                    1.0 - settings.paper_slippage_bps / 10_000.0
                ) * (1.0 - settings.paper_fee_rate)
                risk_per_unit = execution_entry + entry_fee_per_unit - stop_proceeds
                if risk_per_unit > 0:
                    quantity = min(
                        risk_amount / risk_per_unit,
                        (equity * settings.max_single_position_pct)
                        / (execution_entry + entry_fee_per_unit),
                    )
                    entry_fee = execution_entry * quantity * settings.paper_fee_rate
                    fees_paid += entry_fee
                    net_pnl -= entry_fee
                    equity -= entry_fee
                    position_entry = execution_entry
                    stop_loss = signal.stop_loss
                    take_profit = signal.take_profit

        marked_equity = equity
        if position_entry is not None:
            marked_equity += (candle.close - position_entry) * quantity
        peak_equity = max(peak_equity, marked_equity)
        if peak_equity > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak_equity - marked_equity) / peak_equity)

    open_position_pnl = 0.0
    if position_entry is not None and series.candles:
        final_price = series.candles[-1].close
        estimated_exit_fee = final_price * quantity * settings.paper_fee_rate
        open_position_pnl = (final_price - position_entry) * quantity - estimated_exit_fee
    total_pnl = net_pnl + open_position_pnl
    ending_equity = equity + open_position_pnl
    period_start = datetime.fromtimestamp(series.candles[0].open_time / 1000, tz=timezone.utc) if series.candles else None
    period_end = datetime.fromtimestamp(series.candles[-1].close_time / 1000, tz=timezone.utc) if series.candles else None

    return BacktestSummary(
        symbol=series.symbol,
        interval=series.interval,
        candles=len(series.candles),
        initial_equity=starting_equity,
        signals=signals,
        wins=wins,
        losses=losses,
        net_pnl=total_pnl,
        ending_equity=ending_equity,
        return_pct=(total_pnl / starting_equity) * 100 if starting_equity else 0.0,
        max_drawdown_pct=max_drawdown_pct * 100,
        open_position_pnl=open_position_pnl,
        period_start=period_start,
        period_end=period_end,
        data_source=series.source,
        fees_paid=fees_paid,
    )
