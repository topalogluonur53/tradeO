from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.market_data.binance import BinanceMarketDataClient, MarketDataError
from app.trading.paper_broker import PaperPortfolioState, TradingCycleResult
from app.trading.paper_trading import AutomationState, paper_trading_service
from app.trading.schemas import SignalSide
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
def trading_state() -> TradingStateResponse:
    return TradingStateResponse(
        automation=paper_trading_service.automation_state(),
        portfolio=paper_trading_service.broker.snapshot(),
    )


@router.post("/step", response_model=TradingCycleResult)
async def run_trading_step(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
) -> TradingCycleResult:
    try:
        return await paper_trading_service.step(symbol=symbol, interval=interval)
    except (ValueError, MarketDataError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/automation/start", response_model=AutomationState)
async def start_automation(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
) -> AutomationState:
    return paper_trading_service.start(symbol=symbol, interval=interval)


@router.post("/automation/stop", response_model=AutomationState)
async def stop_automation() -> AutomationState:
    return await paper_trading_service.stop()


@router.post("/reset", response_model=PaperPortfolioState)
def reset_paper_portfolio() -> PaperPortfolioState:
    settings = get_settings()
    return paper_trading_service.broker.reset(settings.paper_initial_equity)


@router.get("/backtest", response_model=BacktestSummary)
async def run_backtest(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    limit: int = Query(default=300, ge=60, le=1000),
) -> BacktestSummary:
    settings = get_settings()
    client = BinanceMarketDataClient(
        base_url=settings.market_data_base_url,
        timeout_seconds=settings.market_data_timeout_seconds,
    )
    strategy = EmaRsiStrategy()

    try:
        series = await client.get_candles(symbol=symbol, interval=interval, limit=limit)
    except (ValueError, MarketDataError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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
