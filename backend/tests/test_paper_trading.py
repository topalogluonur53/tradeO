from datetime import UTC, datetime

from app.market_data.schemas import Candle
from app.trading.paper_broker import PaperBroker
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
