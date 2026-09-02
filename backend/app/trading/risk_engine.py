from dataclasses import dataclass

from app.core.config import Settings
from app.trading.control import trading_control
from app.trading.schemas import RiskDecision, Signal, SignalSide


@dataclass(frozen=True)
class PortfolioSnapshot:
    account_equity: float
    current_exposure: float
    open_positions: int
    daily_pnl: float
    peak_equity: float
    consecutive_losses: int


class RiskEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, signal: Signal, portfolio: PortfolioSnapshot) -> RiskDecision:
        if self.settings.kill_switch_enabled or trading_control.snapshot().halted:
            return RiskDecision(approved=False, reason="KILL_SWITCH_ENABLED")

        if signal.side is not SignalSide.BUY:
            return RiskDecision(approved=False, reason="ONLY_LONG_BUY_SIGNALS_ALLOWED_IN_PHASE_1")

        if signal.stop_loss >= signal.entry_price:
            return RiskDecision(approved=False, reason="STOP_LOSS_MUST_BE_BELOW_ENTRY_FOR_LONG")

        reward = signal.take_profit - signal.entry_price
        risk = signal.entry_price - signal.stop_loss
        if risk <= 0:
            return RiskDecision(approved=False, reason="INVALID_STOP_DISTANCE")

        if reward / risk < self.settings.min_risk_reward:
            return RiskDecision(approved=False, reason="MIN_RISK_REWARD_NOT_MET")

        if portfolio.open_positions >= self.settings.max_open_positions:
            return RiskDecision(approved=False, reason="MAX_OPEN_POSITIONS_REACHED")

        if portfolio.consecutive_losses >= self.settings.cooldown_after_losses:
            return RiskDecision(approved=False, reason="COOLDOWN_AFTER_CONSECUTIVE_LOSSES")

        if abs(portfolio.daily_pnl) >= portfolio.account_equity * self.settings.daily_loss_limit_pct and portfolio.daily_pnl < 0:
            return RiskDecision(approved=False, reason="DAILY_LOSS_LIMIT_REACHED")

        drawdown = 0.0
        if portfolio.peak_equity > 0:
            drawdown = max(0.0, (portfolio.peak_equity - portfolio.account_equity) / portfolio.peak_equity)
        if drawdown >= self.settings.max_drawdown_limit_pct:
            return RiskDecision(approved=False, reason="MAX_DRAWDOWN_LIMIT_REACHED")

        risk_amount = portfolio.account_equity * self.settings.risk_per_trade
        quantity_by_risk = risk_amount / risk
        max_position_value = portfolio.account_equity * self.settings.max_single_position_pct
        quantity_by_position_cap = max_position_value / signal.entry_price
        max_total_value = portfolio.account_equity * self.settings.max_total_exposure_pct
        remaining_exposure = max(0.0, max_total_value - portfolio.current_exposure)
        quantity_by_exposure = remaining_exposure / signal.entry_price

        quantity = min(quantity_by_risk, quantity_by_position_cap, quantity_by_exposure)
        if quantity <= 0:
            return RiskDecision(approved=False, reason="NO_AVAILABLE_EXPOSURE")

        return RiskDecision(
            approved=True,
            reason="APPROVED_FOR_PAPER_EXECUTION",
            position_quantity=quantity,
            notional_value=quantity * signal.entry_price,
        )
