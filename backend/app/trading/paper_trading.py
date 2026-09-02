import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.market_data.binance import BinanceMarketDataClient
from app.trading.order_validator import OrderValidationContext, OrderValidator
from app.trading.paper_broker import PaperBroker, TradingCycleResult, create_default_broker
from app.trading.risk_engine import RiskEngine
from app.trading.schemas import SignalSide
from app.trading.strategy_engine import EmaRsiStrategy


class AutomationState(BaseModel):
    enabled: bool
    running: bool
    symbol: str
    interval: str
    last_cycle_at: datetime | None = None
    last_action: str = "IDLE"
    last_reason: str = "Bot is stopped"


class PaperTradingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.broker = create_default_broker(settings)
        self.strategy = EmaRsiStrategy()
        self.risk_engine = RiskEngine(settings)
        self.validator = OrderValidator()
        self.symbol = settings.paper_default_symbol
        self.interval = settings.paper_default_interval
        self.last_cycle_at: datetime | None = None
        self.last_action = "IDLE"
        self.last_reason = "Bot is stopped"
        self._task: asyncio.Task[None] | None = None

    def automation_state(self) -> AutomationState:
        return AutomationState(
            enabled=self._task is not None and not self._task.done(),
            running=self._task is not None and not self._task.done(),
            symbol=self.symbol,
            interval=self.interval,
            last_cycle_at=self.last_cycle_at,
            last_action=self.last_action,
            last_reason=self.last_reason,
        )

    async def step(self, symbol: str | None = None, interval: str | None = None) -> TradingCycleResult:
        selected_symbol = symbol or self.symbol
        selected_interval = interval or self.interval
        client = BinanceMarketDataClient(
            base_url=self.settings.market_data_base_url,
            timeout_seconds=self.settings.market_data_timeout_seconds,
        )

        series = await client.get_candles(symbol=selected_symbol, interval=selected_interval, limit=120)
        latest = series.candles[-1]
        closed_trades = self.broker.evaluate_existing_positions(latest)
        signal = self.strategy.generate_signal(series.symbol, series.candles)

        action = "HOLD"
        reason = signal.explanation
        risk_decision = None

        if closed_trades:
            action = "POSITION_CLOSED"
            reason = closed_trades[-1].exit_reason
        elif signal.side is SignalSide.BUY:
            risk_decision = self.risk_engine.evaluate(
                signal,
                self.broker.portfolio_snapshot_for_risk(self.settings, latest.close),
            )
            if risk_decision.approved:
                valid, validation_reason = self.validator.validate(
                    signal,
                    OrderValidationContext(
                        kill_switch_enabled=self.settings.kill_switch_enabled,
                        latest_price=latest.close,
                        max_price_age_seconds=7200,
                        price_age_seconds=0,
                    ),
                )
                if valid:
                    action = self.broker.try_open_position(signal, risk_decision)
                    reason = validation_reason
                else:
                    action = "ORDER_REJECTED"
                    reason = validation_reason
            else:
                action = "RISK_REJECTED"
                reason = risk_decision.reason

        self.symbol = series.symbol
        self.interval = series.interval
        self.last_cycle_at = datetime.now(UTC)
        self.last_action = action
        self.last_reason = reason

        return TradingCycleResult(
            action=action,
            reason=reason,
            signal=signal,
            risk_decision=risk_decision,
            portfolio=self.broker.snapshot(mark_price=latest.close),
        )

    def start(self, symbol: str | None = None, interval: str | None = None) -> AutomationState:
        if symbol:
            self.symbol = symbol
        if interval:
            self.interval = interval
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            self.last_action = "AUTO_STARTED"
            self.last_reason = "Paper automation loop started"
        return self.automation_state()

    async def stop(self) -> AutomationState:
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self.last_action = "AUTO_STOPPED"
        self.last_reason = "Paper automation loop stopped"
        return self.automation_state()

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.step(self.symbol, self.interval)
            except Exception as exc:  # pragma: no cover - defensive background guard
                self.last_cycle_at = datetime.now(UTC)
                self.last_action = "AUTO_ERROR"
                self.last_reason = str(exc)
            await asyncio.sleep(self.settings.paper_trade_interval_seconds)


paper_trading_service = PaperTradingService(get_settings())
