import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.routes import trading as trading_routes
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.main import app
from app.market_data.offline import build_offline_candles, build_offline_tickers
from app.market_data.schemas import Candle, CandleSeries, MarketTicker
from app.models.trading import PaperPortfolio
from app.trading.paper_broker import PaperBroker
from app.trading.control import trading_control
from app.trading.paper_trading import PaperTradingService
from app.trading.paper_trading import paper_trading_service
from app.trading.schemas import MarketRegime, RiskDecision, Signal, SignalSide
from app.trading.strategy_engine import EmaRsiStrategy


def make_candle(index: int, close: float, volume: float = 100.0) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="1h",
        open_time=1_700_000_000_000 + index * 3_600_000,
        close_time=1_700_000_000_000 + (index + 1) * 3_600_000 - 1,
        open=close * 0.995,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=volume,
        quote_volume=volume * close,
        trade_count=100 + index,
    )


def test_ema_rsi_strategy_can_generate_buy_signal_for_orderly_uptrend() -> None:
    candles = [
        make_candle(index, 100 + index * 0.22 + (1.1 if index % 5 in {0, 1, 2} else -0.8))
        for index in range(60)
    ]

    signal = EmaRsiStrategy().generate_signal("BTCUSDT", candles)

    assert signal.side is SignalSide.BUY
    assert signal.market_regime in {MarketRegime.TRENDING_UP, MarketRegime.UNCERTAIN}
    assert signal.stop_loss < signal.entry_price < signal.take_profit


def test_paper_broker_opens_and_closes_take_profit_position() -> None:
    broker = PaperBroker(initial_equity=10_000)
    signal = Signal(
        symbol="BTCUSDT",
        side=SignalSide.BUY,
        confidence=0.8,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        strategy="TEST",
        market_regime=MarketRegime.TRENDING_UP,
        explanation="test",
        timestamp=datetime.now(UTC),
    )

    action = broker.try_open_position(
        signal,
        risk_decision=RiskDecision(
            approved=True,
            reason="APPROVED_FOR_PAPER_EXECUTION",
            position_quantity=1.0,
            notional_value=100.0,
        ),
    )
    closed = broker.evaluate_existing_positions(make_candle(1, close=112))
    state = broker.snapshot(mark_price=110)

    assert action == "PAPER_POSITION_OPENED"
    assert len(closed) == 1
    assert closed[0].exit_reason == "TAKE_PROFIT"
    assert state.equity == 10_010


def test_paper_broker_only_evaluates_matching_symbol_positions() -> None:
    broker = PaperBroker(initial_equity=10_000)
    signal = Signal(
        symbol="ETHUSDT",
        side=SignalSide.BUY,
        confidence=0.8,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        strategy="TEST",
        market_regime=MarketRegime.TRENDING_UP,
        explanation="test",
        timestamp=datetime.now(UTC),
    )

    broker.try_open_position(
        signal,
        risk_decision=RiskDecision(
            approved=True,
            reason="APPROVED_FOR_PAPER_EXECUTION",
            position_quantity=1.0,
            notional_value=100.0,
        ),
    )
    closed = broker.evaluate_existing_positions(make_candle(1, close=112))
    state = broker.snapshot(mark_price=100)

    assert closed == []
    assert len(state.open_positions) == 1
    assert state.open_positions[0].symbol == "ETHUSDT"


def test_paper_broker_marks_only_matching_symbol_for_risk_snapshot() -> None:
    broker = PaperBroker(initial_equity=10_000)
    signal = Signal(
        symbol="MKR-USDT",
        side=SignalSide.BUY,
        confidence=0.8,
        entry_price=3_000,
        stop_loss=2_900,
        take_profit=3_200,
        strategy="TEST",
        market_regime=MarketRegime.TRENDING_UP,
        explanation="test",
        timestamp=datetime.now(UTC),
    )

    broker.try_open_position(
        signal,
        risk_decision=RiskDecision(
            approved=True,
            reason="APPROVED_FOR_PAPER_EXECUTION",
            position_quantity=0.3,
            notional_value=900.0,
        ),
    )
    state = broker.snapshot(mark_price=25, mark_symbol="ETC-USDT")
    risk_state = broker.portfolio_snapshot_for_risk(
        get_settings(),
        mark_price=25,
        mark_symbol="ETC-USDT",
    )

    assert state.equity == 10_000
    assert state.peak_equity == 10_000
    assert risk_state.account_equity == 10_000
    assert risk_state.peak_equity == 10_000


def test_paper_trading_all_exchange_scan_can_open_candidate_position() -> None:
    async def run_step() -> str:
        service = PaperTradingService(get_settings())
        use_offline_market_fixture(service)

        result = await service.step(symbol="BTCUSDT", interval="1h", exchange="all")
        next_result = await service.step(symbol="BTCUSDT", interval="1h", exchange="all")
        open_symbols = [position.symbol for position in next_result.portfolio.open_positions]
        assert result.signal is not None
        assert result.signal.symbol in open_symbols
        assert "MAX_DRAWDOWN_LIMIT_REACHED" not in next_result.reason
        assert len(open_symbols) == len(set(open_symbols))
        assert service.exchange == "all"
        return result.action

    assert asyncio.run(run_step()) == "PAPER_POSITION_OPENED"


def make_ticker(symbol: str, quote_volume: float, last_price: float = 1.0) -> MarketTicker:
    return MarketTicker(
        exchange="binance",
        symbol=symbol,
        price_change=0.0,
        price_change_percent=0.0,
        weighted_average_price=last_price,
        last_price=last_price,
        last_quantity=1.0,
        open_price=last_price,
        high_price=last_price,
        low_price=last_price,
        volume=quote_volume / last_price if last_price else 0.0,
        quote_volume=quote_volume,
        trade_count=100,
    )


def use_offline_market_fixture(
    service: PaperTradingService,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> None:
    service.settings.allow_offline_paper_trading = True
    async def load_scan_tickers(exchange: str) -> list[MarketTicker]:
        return build_offline_tickers("USDT", exchange=exchange).tickers

    async def load_candle_series(
        symbol: str,
        interval: str,
        exchange: str,
        validate_symbol: bool = True,
    ) -> CandleSeries:
        return build_offline_candles(
            symbol=symbol,
            interval=interval,
            limit=120,
            exchange=exchange,
            cursor=service._next_market_cursor(exchange, symbol, interval),
        )

    if monkeypatch:
        monkeypatch.setattr(service, "_load_scan_tickers", load_scan_tickers)
        monkeypatch.setattr(service, "_load_candle_series", load_candle_series)
        return

    service._load_scan_tickers = load_scan_tickers
    service._load_candle_series = load_candle_series


def test_scan_candidates_filter_invalid_markets_and_rotate_windows() -> None:
    service = PaperTradingService(get_settings())
    tickers = [
        make_ticker("USDCUSDT", 1_000_000),
        make_ticker("XMRUSDT", 900_000),
        make_ticker("ETHUPUSDT", 800_000),
        make_ticker("ZEROUSDT", 700_000, last_price=0.0),
        *[make_ticker(f"ASSET{index}USDT", 600_000 - index) for index in range(80)],
    ]

    first = service._rank_scan_candidates(tickers, "BTCUSDT")
    second = service._rank_scan_candidates(tickers, "BTCUSDT")
    first_symbols = {ticker.symbol for ticker in first}
    second_symbols = {ticker.symbol for ticker in second}

    assert "USDCUSDT" not in first_symbols
    assert "XMRUSDT" not in first_symbols
    assert "ETHUPUSDT" not in first_symbols
    assert "ZEROUSDT" not in first_symbols
    assert first_symbols != second_symbols


def test_scan_loads_binance_and_okx_tickers_concurrently() -> None:
    async def run_scan() -> list[str]:
        service = PaperTradingService(get_settings())
        both_started = asyncio.Event()
        started: list[str] = []

        async def load(exchange: str) -> list[MarketTicker]:
            started.append(exchange)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.25)
            symbol = "BTCUSDT" if exchange == "binance" else "ETH-USDT"
            return [make_ticker(symbol, 1_000_000)]

        service._load_scan_tickers = load
        await service._scan_candidates("BTCUSDT")
        return started

    assert set(asyncio.run(run_scan())) == {"binance", "okx"}


def test_activation_validation_reports_ready_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    trading_control.resume_paper_mode()
    use_offline_market_fixture(paper_trading_service, monkeypatch)
    monkeypatch.setattr(
        trading_routes,
        "PaperTradingService",
        lambda _settings: paper_trading_service,
    )

    with TestClient(app) as client:
        response = client.get("/api/trading/validation?symbol=BTCUSDT&interval=1h&exchange=all")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["phase"] == "PHASE_1"
    assert len(payload["rows"]) == 7
    assert all(row["passed"] for row in payload["rows"])


def test_automation_never_trades_synthetic_fallback_data() -> None:
    async def run_step():
        service = PaperTradingService(get_settings())
        service.settings.allow_offline_paper_trading = False
        series = build_offline_candles("BTCUSDT", "1h", 120)
        service._load_candle_series = lambda *args, **kwargs: asyncio.sleep(0, result=series)
        return await service.step(symbol="BTCUSDT", interval="1h", exchange="binance")

    result = asyncio.run(run_step())

    assert result.action == "MARKET_DATA_UNAVAILABLE"
    assert result.signal is None
    assert result.portfolio.open_positions == []


def test_live_strategy_ignores_currently_forming_candle() -> None:
    service = PaperTradingService(get_settings())
    original = build_offline_candles("BTCUSDT", "1h", 60)
    candles = [*original.candles[:-1], original.candles[-1].model_copy(update={"is_closed": False})]
    series = original.model_copy(
        update={"source": "binance_public_market_data", "candles": candles}
    )

    prepared = service._prepare_series(series)

    assert len(prepared.candles) == len(series.candles) - 1
    assert prepared.candles[-1] == series.candles[-2]


def test_paper_broker_applies_fees_and_slippage() -> None:
    broker = PaperBroker(
        initial_equity=10_000,
        fee_rate=0.001,
        slippage_bps=5,
    )
    signal = Signal(
        symbol="BTCUSDT",
        side=SignalSide.BUY,
        confidence=0.8,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        strategy="TEST",
        market_regime=MarketRegime.TRENDING_UP,
        explanation="test",
    )
    broker.try_open_position(
        signal,
        RiskDecision(
            approved=True,
            reason="APPROVED_FOR_PAPER_EXECUTION",
            position_quantity=1,
            notional_value=101,
        ),
    )

    closed = broker.evaluate_existing_positions(make_candle(1, close=112))

    assert len(closed) == 1
    assert closed[0].fees_paid > 0
    assert closed[0].exit_price < signal.take_profit
    assert closed[0].realized_pnl < 10


def test_activation_validation_blocks_automation_when_halted(monkeypatch: pytest.MonkeyPatch) -> None:
    trading_control.emergency_stop()
    use_offline_market_fixture(paper_trading_service, monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.post("/api/trading/automation/start?symbol=BTCUSDT&interval=1h&exchange=all")

        assert response.status_code == 409
        assert "Activation validation failed" in response.json()["detail"]
    finally:
        trading_control.resume_paper_mode()


def test_automation_start_caps_budget_to_current_equity(monkeypatch: pytest.MonkeyPatch) -> None:
    use_offline_market_fixture(paper_trading_service, monkeypatch)
    monkeypatch.setattr(
        trading_routes,
        "PaperTradingService",
        lambda _settings: paper_trading_service,
    )

    async def skip_initial_cycle(**_kwargs):
        return None

    monkeypatch.setattr(trading_routes, "execute_trading_step_for_user", skip_initial_cycle)

    session = get_session_factory()()
    try:
        session.add(
            PaperPortfolio(
                user_id=1,
                initial_equity=1_000.0,
                cash=999.76,
                equity=999.76,
                peak_equity=1_000.0,
                current_exposure=0.0,
                daily_pnl=0.0,
                consecutive_losses=0,
            )
        )
        session.commit()
    finally:
        session.close()

    with TestClient(app) as client:
        response = client.post(
            "/api/trading/automation/start?symbol=BTCUSDT&interval=1h&exchange=all&position_count=4&allocation_usd=1000"
        )

    assert response.status_code == 200
    assert response.json()["allocation_usd"] == pytest.approx(999.76)


def test_paper_trading_all_exchange_scan_can_close_position_at_take_profit() -> None:
    async def run_steps() -> tuple[list[str], float]:
        service = PaperTradingService(get_settings())
        use_offline_market_fixture(service)
        actions = []
        result = None
        for _ in range(48):
            result = await service.step(symbol="BTCUSDT", interval="1h", exchange="all")
            actions.append(result.action)

        assert result is not None
        profitable_closes = [
            trade
            for trade in result.portfolio.closed_trades
            if trade.exit_reason == "TAKE_PROFIT" and trade.realized_pnl > 0
        ]
        assert profitable_closes
        return actions, result.portfolio.equity

    actions, equity = asyncio.run(run_steps())

    assert "POSITION_CLOSED" in actions
    assert equity > 0
