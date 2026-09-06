import asyncio
import math
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


SCAN_CANDIDATE_LIMIT = 12
PAPER_MARKET_CURSOR_STEP = 4
# Zero means that every eligible live USDT ticker is part of the rotating
# universe. Only SCAN_CANDIDATE_LIMIT candles are fetched per cycle so the
# exchange APIs are not flooded.
SCAN_UNIVERSE_LIMIT = 0
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
_GLOBAL_SCAN_CURSOR = 0


class AutomationState(BaseModel):
    enabled: bool
    running: bool
    symbol: str
    interval: str
    exchange: str = "binance"
    position_count: int = 3
    allocation_usd: float = 0.0
    allocation_per_position_usd: float = 0.0
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
        # get_settings() is cached. Each service mutates risk limits for its
        # owner, so it must never retain the shared Settings instance.
        self.settings = settings.model_copy(deep=True)
        self.broker = create_default_broker(self.settings)
        self.strategy = NexusAIStrategy()
        self.risk_engine = RiskEngine(self.settings)
        self.validator = OrderValidator()
        self.symbol = settings.paper_default_symbol
        self.interval = settings.paper_default_interval
        self.exchange = "binance"
        self.position_count = 3
        self.allocation_usd = 0.0
        self.allocation_per_position_usd = 0.0
        self.last_cycle_at: datetime | None = None
        self.last_action = "IDLE"
        self.last_reason = "Bot is stopped"
        self.last_signal: Signal | None = None
        self.last_risk_decision: RiskDecision | None = None
        self._market_cursors: dict[tuple[str, str, str], int] = {}
        self._scan_cursor = 0
        self._recent_scan_symbols: list[str] = []
        self._latest_ticker_prices: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None

    def automation_state(self) -> AutomationState:
        return AutomationState(
            enabled=self._task is not None and not self._task.done(),
            running=self._task is not None and not self._task.done(),
            symbol=self.symbol,
            interval=self.interval,
            exchange=self.exchange,
            position_count=self.position_count,
            allocation_usd=self.allocation_usd,
            allocation_per_position_usd=self.allocation_per_position_usd,
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

    def close_position(self, position_id: str) -> TradingCycleResult:
        trade = self.broker.close_position(position_id)
        if trade:
            self.last_action = "POSITION_CLOSED_MANUALLY"
            self.last_reason = f"Position {trade.symbol} closed manually by user"
        else:
            self.last_action = "CLOSE_FAILED"
            self.last_reason = f"Position {position_id} not found"
        return TradingCycleResult(
            action=self.last_action,
            reason=self.last_reason,
            portfolio=self.broker.snapshot(),
        )

    def close_all_positions(self) -> TradingCycleResult:
        trades = self.broker.close_all_positions()
        count = len(trades)
        self.last_action = "ALL_POSITIONS_CLOSED"
        self.last_reason = f"{count} open position(s) closed manually by user"
        return TradingCycleResult(
            action=self.last_action,
            reason=self.last_reason,
            portfolio=self.broker.snapshot(),
        )

    async def validate_activation(
        self,
        symbol: str | None = None,
        interval: str | None = None,
        exchange: str | None = None,
        position_count: int | None = None,
        allocation_usd: float | None = None,
    ) -> ActivationValidationSummary:
        selected_symbol = symbol or self.symbol
        selected_interval = interval or self.interval
        selected_exchange = normalize_exchange(exchange or self.exchange)
        self._set_allocation(position_count, allocation_usd)
        validation_exchange = "binance" if selected_exchange == "all" else selected_exchange
        series = await self._load_candle_series(selected_symbol, selected_interval, validation_exchange)
        latest = series.candles[-1]
        signal = self.strategy.generate_signal(series.symbol, series.candles)
        validation_signal = signal.model_copy(update={"side": SignalSide.BUY})
        risk_decision = self.risk_engine.evaluate(
            validation_signal,
            self.broker.portfolio_snapshot_for_risk(
                self.settings,
                latest.close,
                series.symbol,
                max_total_exposure_value=self.allocation_usd or None,
                max_position_value=self.allocation_per_position_usd or None,
            ),
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

        valid_series = [series for series in series_results if not isinstance(series, Exception)]
        if valid_series:
            candle_mark_prices = {
                series.symbol.replace("-", "").upper(): series.candles[-1].close
                for series in valid_series
            }
            # Every open position must receive a stop/take-profit check in a
            # scan. Previously only the one selected candidate was evaluated,
            # so positions outside the 12-symbol window could remain open
            # indefinitely.
            closed_trades = []
            for series in valid_series:
                closed_trades.extend(self.broker.evaluate_existing_positions(series.candles[-1]))

            # Score every candle set first, then execute only the strongest
            # opportunity. This avoids opening the first BUY in ticker order
            # while a better setup is still in the same scan window.
            scored = [
                (series, self.strategy.generate_signal(series.symbol, series.candles))
                for series in valid_series
            ]
            open_position_series = [
                item for item in scored if self.broker.has_exact_open_position(item[0].symbol)
            ]
            buy_candidates = [item for item in scored if item[1].side is SignalSide.BUY]
            current_open_count = len(self.broker.snapshot().open_positions)
            fresh_buy_candidates = [
                item for item in buy_candidates if not self.broker.has_open_position(item[0].symbol)
            ]
            if current_open_count < self.risk_engine.settings.max_open_positions and fresh_buy_candidates:
                # Fill the user-selected position slots before spending cycles
                # re-evaluating an already open symbol.
                selected_series = max(fresh_buy_candidates, key=lambda item: self._signal_score(item[1]))[0]
            elif open_position_series:
                selected_series = max(open_position_series, key=lambda item: self._signal_score(item[1]))[0]
            elif buy_candidates:
                selected_series = max(buy_candidates, key=lambda item: self._signal_score(item[1]))[0]
            else:
                selected_series = max(scored, key=lambda item: self._signal_score(item[1]))[0]

            if closed_trades:
                signal = next(signal for series, signal in scored if series is selected_series)
                self.symbol = selected_series.symbol
                self.interval = selected_series.interval
                self.exchange = "all"
                self.last_cycle_at = datetime.now(UTC)
                self.last_action = "POSITION_CLOSED"
                self.last_reason = closed_trades[-1].exit_reason
                self.last_signal = signal
                self.last_risk_decision = None
                result = TradingCycleResult(
                    action=self.last_action,
                    reason=self.last_reason,
                    signal=signal,
                    portfolio=self.broker.snapshot(),
                )
            else:
                result = self._execute_series(selected_series)
            if self._latest_ticker_prices:
                # The candle used for the trading decision is the authoritative
                # mark for scanned symbols. A 24h ticker can otherwise be from
                # a different synthetic/offline snapshot and create a false
                # drawdown immediately after opening a position.
                result.portfolio = self.broker.snapshot(
                    mark_prices={**self._latest_ticker_prices, **candle_mark_prices}
                )
            scan_score = self._signal_score(result.signal) if result.signal else 0.0
            result.reason = (
                f"Tarama tamamlandi: {len(candidates)} Binance/OKX adayi, "
                f"{len(valid_series)} mum verisi. En iyi aday {result.signal.symbol if result.signal else symbol}: "
                f"{result.reason} (firsat skoru {scan_score:.2f})"
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

    @staticmethod
    def _signal_score(signal: Signal) -> float:
        """Rank setups without weakening the strategy or risk gates."""
        filters = signal.filters
        passed_ratio = sum(item.passed for item in filters) / max(len(filters), 1)
        side_bonus = 1.0 if signal.side is SignalSide.BUY else 0.0
        regime_bonus = 0.10 if signal.market_regime.value in {"TRENDING_UP", "UNCERTAIN"} else 0.0
        return (side_bonus * 2.0) + (signal.confidence * 0.60) + (passed_ratio * 0.30) + regime_bonus

    async def _scan_candidates(self, selected_symbol: str) -> list[MarketTicker]:
        tickers = [
            *await self._load_scan_tickers("binance"),
            *await self._load_scan_tickers("okx"),
        ]
        self._latest_ticker_prices = {
            ticker.symbol.replace("-", "").upper(): ticker.last_price
            for ticker in tickers
            if ticker.last_price > 0
        }
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
                self.broker.has_exact_open_position(ticker.symbol)
                or ticker.symbol.replace("-", "").upper() not in recent_symbols
            )
        ]
        if len(candidates) < SCAN_CANDIDATE_LIMIT:
            candidates = [
                ticker
                for ticker in tickers
                if self._is_scan_candidate(ticker)
            ]

        max_volume = max((math.log1p(item.quote_volume) for item in candidates), default=1.0)
        max_trades = max((math.log1p(item.trade_count) for item in candidates), default=1.0)

        def market_priority(item: MarketTicker) -> float:
            liquidity = math.log1p(item.quote_volume) / max_volume if max_volume else 0.0
            activity = math.log1p(item.trade_count) / max_trades if max_trades else 0.0
            # Positive 24h momentum gets priority, but extreme pumps are not
            # allowed to dominate the scan by themselves.
            momentum = max(0.0, min(1.0, 0.5 + (item.price_change_percent / 20.0)))
            return (liquidity * 0.55) + (momentum * 0.30) + (activity * 0.15)

        open_candidates = [
            item for item in candidates if self.broker.has_exact_open_position(item.symbol)
        ]
        fresh_candidates = [item for item in candidates if item not in open_candidates]
        open_candidates.sort(key=market_priority, reverse=True)
        fresh_candidates.sort(
            key=lambda item: (
                item.symbol.replace("-", "").upper() != selected_normalized,
                -market_priority(item),
            ),
        )
        if SCAN_UNIVERSE_LIMIT > 0:
            fresh_candidates = fresh_candidates[:SCAN_UNIVERSE_LIMIT]
        if not open_candidates and not fresh_candidates:
            return []

        # The worker reconstructs a service for each user/cycle. Keep the
        # rotating window at module scope so a new service does not restart
        # every scan from the same highest-volume symbols.
        global _GLOBAL_SCAN_CURSOR
        cursor = _GLOBAL_SCAN_CURSOR % len(fresh_candidates) if fresh_candidates else 0
        _GLOBAL_SCAN_CURSOR = (
            (cursor + SCAN_CANDIDATE_LIMIT) % len(fresh_candidates)
            if fresh_candidates
            else 0
        )
        self._scan_cursor = _GLOBAL_SCAN_CURSOR
        rotated_fresh = [*fresh_candidates[cursor:], *fresh_candidates[:cursor]]
        # Do not truncate open positions: they need an exit check even when a
        # user has configured more positions than the new-entry scan window.
        return [*open_candidates, *rotated_fresh[:SCAN_CANDIDATE_LIMIT]]

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
                    self.broker.portfolio_snapshot_for_risk(
                        self.settings,
                        latest.close,
                        series.symbol,
                        max_total_exposure_value=self.allocation_usd or None,
                        max_position_value=self.allocation_per_position_usd or None,
                    ),
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

    def _set_allocation(self, position_count: int | None, allocation_usd: float | None) -> None:
        if position_count is not None:
            self.position_count = max(1, position_count)
        if allocation_usd is not None:
            self.allocation_usd = max(0.0, allocation_usd)
        self.allocation_per_position_usd = (
            self.allocation_usd / self.position_count
            if self.allocation_usd > 0 and self.position_count > 0
            else 0.0
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
