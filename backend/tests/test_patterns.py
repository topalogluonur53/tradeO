from app.core.config import get_settings
from app.market_data.schemas import Candle
from app.market_data.schemas import CandleSeries
from app.trading.indicators import calculate_indicator_snapshot
from app.trading.paper_broker import PaperBroker
from app.trading.paper_trading import PaperTradingService
from app.trading.patterns import detect_price_patterns
from app.trading.schemas import MarketRegime, RiskDecision, Signal, SignalSide
from app.trading.strategy_engine import NexusAIStrategy


def candle(index: int, open_price: float, close: float, volume: float = 100.0) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="1h",
        open_time=1_700_000_000_000 + index * 3_600_000,
        close_time=1_700_003_599_999 + index * 3_600_000,
        open=open_price,
        high=max(open_price, close) + 0.5,
        low=min(open_price, close) - 0.5,
        close=close,
        volume=volume,
        quote_volume=volume * close,
        trade_count=100,
    )


def orderly_uptrend(count: int = 60) -> list[Candle]:
    return [
        candle(index, 100 + index * 0.2 - 0.12, 100 + index * 0.2)
        for index in range(count)
    ]


def test_detects_bullish_engulfing_and_breakout() -> None:
    candles = orderly_uptrend(28)
    candles.append(candle(28, 106.2, 105.2, volume=120))
    candles.append(candle(29, 105.0, 107.0, volume=180))

    patterns = detect_price_patterns(candles)
    keys = {pattern.key for pattern in patterns}

    assert "bullish_engulfing" in keys
    assert "range_breakout" in keys


def test_strong_bearish_engulfing_emits_an_exit_signal() -> None:
    candles = orderly_uptrend()
    previous = candles[-1]
    candles[-1] = candle(59, previous.open, previous.close, volume=120)
    candles.append(
        candle(60, candles[-1].close + 0.5, candles[-1].open - 0.7, volume=180)
    )

    signal = NexusAIStrategy().generate_signal("BTCUSDT", candles)

    assert any(pattern.key == "bearish_engulfing" for pattern in signal.patterns)
    assert signal.side is SignalSide.SELL
    assert next(item for item in signal.filters if item.key == "bearish_veto").passed is False


def test_adx_direction_recognizes_orderly_uptrend() -> None:
    snapshot = calculate_indicator_snapshot(orderly_uptrend(80))

    assert snapshot["adx"] >= 18
    assert snapshot["plus_di"] > snapshot["minus_di"]


def test_mtf_setting_adds_real_higher_timeframe_confirmation() -> None:
    signal = NexusAIStrategy(mtf_enabled=True).generate_signal(
        "BTCUSDT",
        orderly_uptrend(120),
    )

    mtf_filter = next(item for item in signal.filters if item.key == "mtf")
    assert mtf_filter.passed is True
    assert "ADX" in mtf_filter.actual


def test_bearish_strategy_signal_closes_an_open_position() -> None:
    candles = orderly_uptrend()
    previous = candles[-1]
    candles.append(
        candle(60, previous.close + 0.5, previous.open - 0.7, volume=180)
    )
    service = PaperTradingService(get_settings())
    service.settings.allow_offline_paper_trading = True
    service.broker = PaperBroker(initial_equity=10_000)
    entry = Signal(
        symbol="BTCUSDT",
        side=SignalSide.BUY,
        confidence=0.8,
        entry_price=previous.close,
        stop_loss=previous.close * 0.90,
        take_profit=previous.close * 1.20,
        strategy="TEST",
        market_regime=MarketRegime.TRENDING_UP,
        explanation="test entry",
    )
    service.broker.try_open_position(
        entry,
        RiskDecision(
            approved=True,
            reason="APPROVED_FOR_PAPER_EXECUTION",
            position_quantity=1.0,
            notional_value=previous.close,
        ),
    )
    series = CandleSeries(
        symbol="BTCUSDT",
        interval="1h",
        source="offline_paper_test",
        exchange="binance",
        candles=candles,
    )

    result = service._execute_series(series)

    assert result.signal is not None
    assert result.signal.side is SignalSide.SELL
    assert result.action == "POSITION_CLOSED"
    assert result.reason == "STRATEGY_EXIT"
    assert result.portfolio.open_positions == []
