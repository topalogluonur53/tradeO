import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.market_data.binance import BinanceMarketDataClient, MarketDataError, normalize_exchange
from app.market_data.offline import build_offline_candles, build_offline_tickers
from app.market_data.okx import OkxMarketDataClient
from app.market_data.schemas import CandleSeries, MarketTicker
from app.trading.order_validator import OrderValidationContext, OrderValidator
from app.trading.paper_broker import PaperBroker, TradingCycleResult, create_default_broker
from app.trading.risk_engine import RiskEngine
from app.trading.schemas import RiskDecision, Signal, SignalSide
from app.trading.strategy_engine import NexusAIStrategy


SCAN_CANDIDATE_LIMIT = 8
PAPER_MARKET_CURSOR_STEP = 4
SCAN_UNIVERSE_LIMIT = 160
RECENT_SCAN_SYMBOL_LIMIT = 24
STABLE_SCAN_BASE_ASSETS = {
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "USD1",
    "RLUSD",
    "EUR",
    "TRY",
    "BRL",
    "AUD",
    "AUDF",
    "AUDM",
}
LEVERAGED_SCAN_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
INACTIVE_SCAN_BASE_ASSETS = {"XMR"}


class AutomationState(BaseModel):
    enabled: bool
    running: bool
    symbol: str
    interval: str
    exchange: str = "binance"
    last_cycle_at: datetime | None = None
    last_action: str = "IDLE"
    last_reason: str = "Bot is stopped"
    last_signal: Signal | None = None
    last_risk_decision: RiskDecision | None = None


class ActivationValidationRow(BaseModel):
    key: str
    name: str
    status: str
    market_regime: str
    activation: str
    passed: bool
    actual: str
    required: str


class ActivationValidationSummary(BaseModel):
    ready: bool
    phase: str = "PHASE_1"
    symbol: str
    interval: str
    exchange: str
    checked_at: datetime
    rows: list[ActivationValidationRow]


class PaperTradingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.broker = create_default_broker(settings)
        self.strategy = NexusAIStrategy()
        self.risk_engine = RiskEngine(settings)
        self.validator = OrderValidator()
        self.symbol = settings.paper_default_symbol
        self.interval = settings.paper_default_interval
        self.exchange = "binance"
        self.last_cycle_at: datetime | None = None
        self.last_action = "IDLE"
        self.last_reason = "Bot is stopped"
        self.last_signal: Signal | None = None
        self.last_risk_decision: RiskDecision | None = None
        self._market_cursors: dict[tuple[str, str, str], int] = {}
        self._scan_cursor = 0
        self._recent_scan_symbols: list[str] = []
        self._task: asyncio.Task[None] | None = None

    def automation_state(self) -> AutomationState:
        return AutomationState(
            enabled=self._task is not None and not self._task.done(),
            running=self._task is not None and not self._task.done(),
            symbol=self.symbol,
            interval=self.interval,
            exchange=self.exchange,
            last_cycle_at=self.last_cycle_at,
            last_action=self.last_action,
            last_reason=self.last_reason,
            last_signal=self.last_signal,
            last_risk_decision=self.last_risk_decision,
        )

    async def step(
        self,
        symbol: str | None = None,
        interval: str | None = None,
        exchange: str | None = None,
    ) -> TradingCycleResult:
        selected_symbol = symbol or self.symbol
        selected_interval = interval or self.interval
        selected_exchange = normalize_exchange(exchange or self.exchange)
        if selected_exchange == "all":
            return await self._step_scan_all(selected_symbol, selected_interval)

        series = await self._load_candle_series(selected_symbol, selected_interval, selected_exchange)
        return self._execute_series(series)

    async def validate_activation(
        self,
        symbol: str | None = None,
        interval: str | None = None,
        exchange: str | None = None,
    ) -> ActivationValidationSummary:
        selected_symbol = symbol or self.symbol
        selected_interval = interval or self.interval
        selected_exchange = normalize_exchange(exchange or self.exchange)
        validation_exchange = "binance" if selected_exchange == "all" else selected_exchange
        series = await self._load_candle_series(selected_symbol, selected_interval, validation_exchange)
        latest = series.candles[-1]
        signal = self.strategy.generate_signal(series.symbol, series.candles)
        validation_signal = signal.model_copy(update={"side": SignalSide.BUY})
        risk_decision = self.risk_engine.evaluate(
            validation_signal,
            self.broker.portfolio_snapshot_for_risk(self.settings, latest.close, series.symbol),
        )
        order_valid, order_reason = self.validator.validate(
            validation_signal,
            OrderValidationContext(
                kill_switch_enabled=self.settings.kill_switch_enabled,
                latest_price=latest.close,
                max_price_age_seconds=7200,
                price_age_seconds=0,
            ),
        )

        filters = {item.key: item for item in signal.filters}
        indicators = signal.indicators
        atr_pct = indicators.get("atr_pct", 0.0)
        volume_filter = filters.get("volume")
        stop_take_profit_valid = signal.stop_loss < signal.entry_price < signal.take_profit
        strategy_ready = signal.strategy == self.strategy.name and bool(signal.filters)

        rows = [
            self._validation_row(
                key="ema_rsi",
                name="EMA + RSI",
                passed=strategy_ready,
                market_regime=signal.market_regime.value,
                actual=f"{signal.side.value} / {format_percent(signal.confidence)} güven",
                required="Sinyal motoru filtreleri üretmeli",
            ),
            self._validation_row(
                key="risk_engine",
                name="Risk Motoru",
                passed=risk_decision.approved,
                market_regime=signal.market_regime.value,
                actual=risk_decision.reason,
                required="APPROVED_FOR_PAPER_EXECUTION",
            ),
            self._validation_row(
                key="order_validation",
                name="Emir Doğrulaması",
                passed=order_valid,
                market_regime=signal.market_regime.value,
                actual=order_reason,
                required="VALID_FOR_PAPER_EXECUTION",
            ),
            self._validation_row(
                key="stop_take_profit",
                name="Stop / Take Profit",
                passed=stop_take_profit_valid,
                market_regime=signal.market_regime.value,
                actual=f"{latest.close:.6g} / {signal.stop_loss:.6g} / {signal.take_profit:.6g}",
                required="Stop < giriş < take-profit",
            ),
            self._validation_row(
                key="volatility_filter",
                name="Volatilite Filtresi",
                passed=atr_pct > 0,
                market_regime=signal.market_regime.value,
                actual=format_percent(atr_pct),
                required="ATR hesaplanmali",
            ),
            self._validation_row(
                key="volume_validation",
                name="Hacim Doğrulaması",
                passed=volume_filter.passed if volume_filter else False,
                market_regime=signal.market_regime.value,
                actual=volume_filter.actual if volume_filter else "-",
                required=volume_filter.required if volume_filter else ">= 0.35",
            ),
        ]

        # The volume filter is a per-candle entry condition, not a safety
        # prerequisite for starting the automation loop.  Keeping it visible
        # in the checklist lets the UI explain why the current cycle will
        # hold, while allowing the bot to wait for a qualifying candle.
        activation_ready = all(
            row.passed for row in rows if row.key != "volume_validation"
        )

        return ActivationValidationSummary(
            ready=activation_ready,
            symbol=series.symbol,
            interval=series.interval,
            exchange=selected_exchange,
            checked_at=datetime.now(UTC),
            rows=rows,
        )

    async def _load_candle_series(
        self,
        symbol: str,
        interval: str,
        exchange: str,
        validate_symbol: bool = True,
    ) -> CandleSeries:
        try:
            if exchange == "okx":
                client = OkxMarketDataClient(
                    timeout_seconds=self.settings.market_data_timeout_seconds,
                )
                return await client.get_candles(
                    symbol=symbol,
                    interval=interval,
                    limit=120,
                    validate_symbol=validate_symbol,
                )

            client = BinanceMarketDataClient(
                base_url=self.settings.market_data_base_url,
                timeout_seconds=self.settings.market_data_timeout_seconds,
            )
            return await client.get_candles(
                symbol=symbol,
                interval=interval,
                limit=120,
                validate_symbol=validate_symbol,
            )
        except MarketDataError:
            return build_offline_candles(
                symbol=symbol,
                interval=interval,
                limit=120,
                exchange=exchange,
                cursor=self._next_market_cursor(exchange, symbol, interval),
            )

    async def _step_scan_all(self, symbol: str, interval: str) -> TradingCycleResult:
        candidates = await self._scan_candidates(symbol)
        best_result: TradingCycleResult | None = None
        last_rejected: TradingCycleResult | None = None
        series_results = await asyncio.gather(
            *[
                self._load_candle_series(
                    candidate.symbol,
                    interval,
                    candidate.exchange,
                    validate_symbol=False,
                )
                for candidate in candidates
            ],
            return_exceptions=True,
        )

        for series in series_results:
            if isinstance(series, Exception):
                continue

            result = self._execute_series(series)

            if result.action in {"POSITION_CLOSED", "PAPER_POSITION_OPENED"}:
                self.exchange = "all"
                if result.signal:
                    self._remember_scan_symbol(result.signal.symbol)
                return result

            if result.action in {"RISK_REJECTED", "ORDER_REJECTED", "INSUFFICIENT_PAPER_CASH"}:
                last_rejected = result

            if result.signal and (
                best_result is None
                or not best_result.signal
                or result.signal.confidence > best_result.signal.confidence
            ):
                best_result = result

        result = last_rejected or best_result
        if result:
            result.reason = (
                f"Tarama tamamlandi: {len(candidates)} Binance/OKX adayinda emir acilmadi. "
                f"En iyi aday {result.signal.symbol if result.signal else symbol}: {result.reason}"
            )
            self.last_action = result.action
            self.last_reason = result.reason
            self.exchange = "all"
            if result.signal:
                self._remember_scan_symbol(result.signal.symbol)
            return result

        fallback_series = build_offline_candles(
            symbol=symbol,
            interval=interval,
            limit=120,
            exchange="binance",
            cursor=self._next_market_cursor("binance", symbol, interval),
        )
        result = self._execute_series(fallback_series)
        result.reason = "Tarama icin aday bulunamadi."
        self.last_reason = result.reason
        self.exchange = "all"
        return result

    async def _scan_candidates(self, selected_symbol: str) -> list[MarketTicker]:
        tickers = [
            *await self._load_scan_tickers("binance"),
            *await self._load_scan_tickers("okx"),
        ]
        return self._rank_scan_candidates(tickers, selected_symbol)

    async def _load_scan_tickers(self, exchange: str) -> list[MarketTicker]:
        try:
            if exchange == "okx":
                return (await OkxMarketDataClient(
                    timeout_seconds=self.settings.market_data_timeout_seconds,
                ).get_24h_tickers("USDT")).tickers

            return (await BinanceMarketDataClient(
                base_url=self.settings.market_data_base_url,
                timeout_seconds=self.settings.market_data_timeout_seconds,
            ).get_24h_tickers("USDT")).tickers
        except MarketDataError:
            return build_offline_tickers("USDT", exchange=exchange).tickers

    def _rank_scan_candidates(self, tickers: list[MarketTicker], selected_symbol: str) -> list[MarketTicker]:
        selected_normalized = selected_symbol.replace("-", "").upper()
        recent_symbols = set(self._recent_scan_symbols)
        candidates = [
            ticker
            for ticker in tickers
            if self._is_scan_candidate(ticker)
            and (
                self.broker.has_open_position(ticker.symbol)
                or ticker.symbol.replace("-", "").upper() not in recent_symbols
            )
        ]
        if len(candidates) < SCAN_CANDIDATE_LIMIT:
            candidates = [
                ticker
                for ticker in tickers
                if self._is_scan_candidate(ticker)
            ]

        prioritized = sorted(
            candidates,
            key=lambda item: (
                not self.broker.has_open_position(item.symbol),
                item.symbol.replace("-", "").upper() != selected_normalized,
                -item.quote_volume,
            ),
        )[:SCAN_UNIVERSE_LIMIT]
        if not prioritized:
            return []

        cursor = self._scan_cursor % len(prioritized)
        self._scan_cursor = (cursor + SCAN_CANDIDATE_LIMIT) % len(prioritized)
        return [*prioritized[cursor:], *prioritized[:cursor]][:SCAN_CANDIDATE_LIMIT]

    def _is_scan_candidate(self, ticker: MarketTicker) -> bool:
        base_asset = base_asset_from_symbol(ticker.symbol)
        if base_asset in STABLE_SCAN_BASE_ASSETS:
            return False
        if base_asset in INACTIVE_SCAN_BASE_ASSETS:
            return False
        if any(base_asset.endswith(suffix) for suffix in LEVERAGED_SCAN_SUFFIXES):
            return False
        return ticker.last_price > 0 and ticker.quote_volume > 0

    def _remember_scan_symbol(self, symbol: str) -> None:
        normalized_symbol = symbol.replace("-", "").upper()
        self._recent_scan_symbols = [
            item for item in self._recent_scan_symbols if item != normalized_symbol
        ]
        self._recent_scan_symbols.insert(0, normalized_symbol)
        self._recent_scan_symbols = self._recent_scan_symbols[:RECENT_SCAN_SYMBOL_LIMIT]

    def _next_market_cursor(self, exchange: str, symbol: str, interval: str) -> int:
        key = (exchange, symbol, interval)
        current = self._market_cursors.get(key, 0)
        self._market_cursors[key] = current + PAPER_MARKET_CURSOR_STEP
        return current

    def _execute_series(self, series: CandleSeries) -> TradingCycleResult:
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
            if self.broker.has_open_position(signal.symbol):
                reason = "OPEN_POSITION_ALREADY_EXISTS"
            else:
                risk_decision = self.risk_engine.evaluate(
                    signal,
                    self.broker.portfolio_snapshot_for_risk(self.settings, latest.close, series.symbol),
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
        self.exchange = series.exchange
        self.last_cycle_at = datetime.now(UTC)
        self.last_action = action
        self.last_reason = reason
        self.last_signal = signal
        self.last_risk_decision = risk_decision

        return TradingCycleResult(
            action=action,
            reason=reason,
            signal=signal,
            risk_decision=risk_decision,
            portfolio=self.broker.snapshot(mark_price=latest.close, mark_symbol=series.symbol),
        )

    def start(
        self,
        symbol: str | None = None,
        interval: str | None = None,
        exchange: str | None = None,
    ) -> AutomationState:
        if symbol:
            self.symbol = symbol
        if interval:
            self.interval = interval
        if exchange:
            selected_exchange = normalize_exchange(exchange)
            self.exchange = selected_exchange
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            self.last_action = "AUTO_STARTED"
            self.last_reason = "Paper automation loop started"
            self.last_signal = None
            self.last_risk_decision = None
        return self.automation_state()

    @staticmethod
    def _validation_row(
        key: str,
        name: str,
        passed: bool,
        market_regime: str,
        actual: str,
        required: str,
    ) -> ActivationValidationRow:
        return ActivationValidationRow(
            key=key,
            name=name,
            status="Hazır" if passed else "Bekliyor",
            market_regime=market_regime,
            activation="TAMAMLANDI" if passed else "DOĞRULAMA GEREKLİ",
            passed=passed,
            actual=actual,
            required=required,
        )

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
                await self.step(self.symbol, self.interval, self.exchange)
            except Exception as exc:  # pragma: no cover - defensive background guard
                self.last_cycle_at = datetime.now(UTC)
                self.last_action = "AUTO_ERROR"
                self.last_reason = str(exc)
            await asyncio.sleep(self.settings.paper_trade_interval_seconds)


paper_trading_service = PaperTradingService(get_settings())


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def base_asset_from_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if "-" in normalized:
        return normalized.split("-", 1)[0]
    if normalized.endswith("USDT"):
        return normalized[:-4]
    return normalized
