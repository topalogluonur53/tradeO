from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

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
from app.trading.multi_tenant import execute_trading_step_for_user, get_or_create_automation_state, get_or_create_portfolio
from app.trading.schemas import SignalSide, Signal, RiskDecision
from app.trading.strategy_engine import EmaRsiStrategy

router = APIRouter(prefix="/trading", tags=["trading"])


class TradingStateResponse(BaseModel):
    automation: AutomationState
    portfolio: PaperPortfolioState


class BacktestSummary(BaseModel):
    symbol: str
    interval: str
    candles: int
    signals: int
    wins: int
    losses: int
    net_pnl: float
    ending_equity: float


@router.get("/state", response_model=TradingStateResponse)
def trading_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TradingStateResponse:
    auto_state = get_or_create_automation_state(db, current_user)
    portfolio = get_or_create_portfolio(db, current_user)
    
    # Parse last signal and risk decision
    last_signal = None
    if auto_state.last_signal_json:
        last_signal = Signal.model_validate_json(auto_state.last_signal_json)
        
    last_risk = None
    if auto_state.last_risk_decision_json:
        last_risk = RiskDecision.model_validate_json(auto_state.last_risk_decision_json)
    
    return TradingStateResponse(
        automation=AutomationState(
            enabled=auto_state.enabled,
            running=auto_state.running,
            symbol=auto_state.symbol,
            interval=auto_state.interval,
            exchange=auto_state.exchange,
            last_cycle_at=auto_state.last_cycle_at,
            last_action=auto_state.last_action,
            last_reason=auto_state.last_reason,
            last_signal=last_signal,
            last_risk_decision=last_risk
        ),
        portfolio=PaperPortfolioState(
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
                    strategy=p.strategy
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
                    strategy=t.strategy
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ActivationValidationSummary:
    try:
        service = PaperTradingService(get_settings())
        return await service.validate_activation(
            symbol=symbol,
            interval=interval,
            exchange=exchange,
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
        return await execute_trading_step_for_user(
            db=db, user=current_user, symbol=symbol, interval=interval, exchange=exchange
        )
    except (ValueError, MarketDataError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/automation/start", response_model=AutomationState)
async def start_automation(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    exchange: str = Query(default="binance", min_length=2, max_length=12),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AutomationState:
    service = PaperTradingService(get_settings())
    validation = await service.validate_activation(
        symbol=symbol,
        interval=interval,
        exchange=exchange,
    )
    if not validation.ready:
        failed = ", ".join(row.name for row in validation.rows if not row.passed)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Activation validation failed: {failed}",
        )
    
    auto_state = get_or_create_automation_state(db, current_user)
    auto_state.enabled = True
    auto_state.running = True
    auto_state.symbol = symbol
    auto_state.interval = interval
    auto_state.exchange = exchange
    auto_state.last_action = "AUTO_STARTED"
    auto_state.last_reason = "Paper automation loop started"
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


@router.post("/reset", response_model=PaperPortfolioState)
def reset_paper_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PaperPortfolioState:
    settings = get_settings()
    portfolio = get_or_create_portfolio(db, current_user)
    portfolio.cash = settings.paper_initial_equity
    portfolio.equity = settings.paper_initial_equity
    portfolio.peak_equity = settings.paper_initial_equity
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
) -> BacktestSummary:
    settings = get_settings()
    strategy = EmaRsiStrategy()
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

    equity = settings.paper_initial_equity
    position_entry: float | None = None
    stop_loss = 0.0
    take_profit = 0.0
    quantity = 0.0
    signals = 0
    wins = 0
    losses = 0
    net_pnl = 0.0

    for index in range(30, len(series.candles)):
        window = series.candles[: index + 1]
        candle = window[-1]

        if position_entry is not None:
            exit_price = None
            if candle.low <= stop_loss:
                exit_price = stop_loss
            elif candle.high >= take_profit:
                exit_price = take_profit

            if exit_price is not None:
                realized_pnl = (exit_price - position_entry) * quantity
                net_pnl += realized_pnl
                equity += realized_pnl
                wins += 1 if realized_pnl > 0 else 0
                losses += 1 if realized_pnl <= 0 else 0
                position_entry = None

        if position_entry is None:
            signal = strategy.generate_signal(series.symbol, window)
            if signal.side is SignalSide.BUY:
                signals += 1
                risk_amount = equity * settings.risk_per_trade
                risk_per_unit = signal.entry_price - signal.stop_loss
                if risk_per_unit > 0:
                    quantity = min(
                        risk_amount / risk_per_unit,
                        (equity * settings.max_single_position_pct) / signal.entry_price,
                    )
                    position_entry = signal.entry_price
                    stop_loss = signal.stop_loss
                    take_profit = signal.take_profit

    return BacktestSummary(
        symbol=series.symbol,
        interval=series.interval,
        candles=len(series.candles),
        signals=signals,
        wins=wins,
        losses=losses,
        net_pnl=net_pnl,
        ending_equity=equity,
    )
