from app.core.config import get_settings
from app.trading.control import trading_control
from app.trading.order_validator import OrderValidationContext, OrderValidator
from app.trading.risk_engine import PortfolioSnapshot, RiskEngine
from app.trading.schemas import MarketRegime, Signal, SignalSide


def valid_signal() -> Signal:
    return Signal(
        symbol="BTC/USDT",
        side=SignalSide.BUY,
        confidence=0.8,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        strategy="EMA_RSI",
        market_regime=MarketRegime.TRENDING_UP,
        explanation="Deterministic test signal",
    )


def test_shared_kill_switch_blocks_risk_and_order_validation() -> None:
    trading_control.emergency_stop()
    signal = valid_signal()

    try:
        risk_decision = RiskEngine(get_settings()).evaluate(
            signal,
            PortfolioSnapshot(
                account_equity=10_000.0,
                current_exposure=0.0,
                open_positions=0,
                daily_pnl=0.0,
                peak_equity=10_000.0,
                consecutive_losses=0,
            ),
        )
        order_valid, order_reason = OrderValidator().validate(
            signal,
            OrderValidationContext(
                kill_switch_enabled=False,
                latest_price=100.0,
                max_price_age_seconds=10,
                price_age_seconds=1,
            ),
        )
    finally:
        trading_control.resume_paper_mode()

    assert risk_decision.approved is False
    assert risk_decision.reason == "KILL_SWITCH_ENABLED"
    assert order_valid is False
    assert order_reason == "KILL_SWITCH_ENABLED"
