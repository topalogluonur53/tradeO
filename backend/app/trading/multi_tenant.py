import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from uuid import uuid4

from app.models.user import User
from app.models.trading import PaperPortfolio, PaperPosition, PaperTrade, AutomationState
from app.trading.paper_broker import PaperBroker, PaperPortfolioState, PaperPosition as BrokerPosition, PaperTrade as BrokerTrade
from app.trading.paper_trading import PaperTradingService
from app.core.config import get_settings
from app.trading.strategy_engine import NexusAIStrategy


def get_or_create_portfolio(db: Session, user: User) -> PaperPortfolio:
    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.user_id == user.id).first()
    if not portfolio:
        settings = get_settings()
        portfolio = PaperPortfolio(
            user_id=user.id,
            cash=settings.paper_initial_equity,
            equity=settings.paper_initial_equity,
            peak_equity=settings.paper_initial_equity,
            current_exposure=0.0,
            daily_pnl=0.0,
            consecutive_losses=0,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def get_or_create_automation_state(db: Session, user: User) -> AutomationState:
    state = db.query(AutomationState).filter(AutomationState.user_id == user.id).first()
    if not state:
        state = AutomationState(user_id=user.id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


async def execute_trading_step_for_user(
    db: Session, 
    user: User, 
    symbol: str | None = None, 
    interval: str | None = None, 
    exchange: str | None = None
):
    settings = get_settings()
    
    # 1. Load User's Portfolio from DB
    portfolio = get_or_create_portfolio(db, user)
    
    # Map DB models to Pydantic for PaperBroker
    db_positions = portfolio.open_positions
    db_trades = portfolio.closed_trades
    
    open_positions = [
        BrokerPosition(
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
        ) for p in db_positions
    ]
    
    closed_trades = [
        BrokerTrade(
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
        ) for t in db_trades[-50:] # Only load last 50 for memory
    ]
    
    # 2. Reconstruct PaperTradingService specific to this user
    service = PaperTradingService(settings)
    service.strategy = NexusAIStrategy(
        bollinger_width=user.strategy_bollinger_width,
        rsi_min=user.strategy_rsi_min,
        rsi_max=user.strategy_rsi_max,
        volume_multiplier=user.strategy_volume_multiplier,
        macd_enabled=user.strategy_macd_enabled,
        stoch_enabled=user.strategy_stoch_enabled
    )
    
    # Apply user-specific risk limits from the User model!
    service.risk_engine.settings.risk_per_trade = user.risk_per_trade
    service.risk_engine.settings.max_single_position_pct = user.max_single_position_pct
    service.risk_engine.settings.max_total_exposure_pct = user.max_total_exposure_pct
    service.risk_engine.settings.max_open_positions = user.max_open_positions
    service.risk_engine.settings.daily_loss_limit_pct = user.daily_loss_limit_pct
    service.risk_engine.settings.max_drawdown_limit_pct = user.max_drawdown_limit_pct
    service.risk_engine.settings.min_risk_reward = user.min_risk_reward
    service.risk_engine.settings.cooldown_after_losses = user.cooldown_after_losses
    service.settings.kill_switch_enabled = user.trading_halted

    # Overwrite broker state
    service.broker = PaperBroker(
        initial_equity=settings.paper_initial_equity,
        cash=portfolio.cash,
        peak_equity=portfolio.peak_equity,
        open_positions=open_positions,
        closed_trades=closed_trades,
        consecutive_losses=portfolio.consecutive_losses,
        trailing_stop_enabled=user.trailing_stop_enabled,
        trailing_stop_distance_pct=user.trailing_stop_distance_pct
    )
    
    # Load Automation State
    auto_state = get_or_create_automation_state(db, user)
    service.symbol = symbol or auto_state.symbol
    service.interval = interval or auto_state.interval
    service.exchange = exchange or auto_state.exchange
    
    # 3. Execute Step
    result = await service.step(symbol=service.symbol, interval=service.interval, exchange=service.exchange)
    
    # 4. Save results back to DB
    new_state: PaperPortfolioState = result.portfolio
    portfolio.cash = new_state.cash
    portfolio.equity = new_state.equity
    portfolio.peak_equity = new_state.peak_equity
    portfolio.current_exposure = new_state.current_exposure
    portfolio.daily_pnl = new_state.daily_pnl
    portfolio.consecutive_losses = new_state.consecutive_losses
    
    # Clear and recreate open positions
    db.query(PaperPosition).filter(PaperPosition.portfolio_id == portfolio.id).delete()
    for p in new_state.open_positions:
        db.add(PaperPosition(
            id=p.id,
            portfolio_id=portfolio.id,
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
        ))
        
    # Append new trades
    existing_trade_ids = {t.id for t in db_trades}
    for t in new_state.closed_trades:
        if t.id not in existing_trade_ids:
            db.add(PaperTrade(
                id=t.id,
                portfolio_id=portfolio.id,
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
            ))

    # Update AutomationState
    auto_state.last_cycle_at = datetime.now(timezone.utc)
    auto_state.last_action = result.action
    auto_state.last_reason = result.reason
    auto_state.symbol = service.symbol
    auto_state.interval = service.interval
    auto_state.exchange = service.exchange
    
    if result.signal:
        auto_state.last_signal_json = result.signal.model_dump_json()
    if result.risk_decision:
        auto_state.last_risk_decision_json = result.risk_decision.model_dump_json()
        
    db.commit()
    return result

