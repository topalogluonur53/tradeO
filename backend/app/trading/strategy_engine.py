from app.market_data.schemas import Candle
from app.trading.indicators import calculate_indicator_snapshot
from app.trading.regime import detect_market_regime
from app.trading.schemas import MarketRegime, Signal, SignalSide


class EmaRsiStrategy:
    name = "EMA_RSI_SPOT_LONG"

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal:
        latest = candles[-1]
        indicators = calculate_indicator_snapshot(candles)
        regime = detect_market_regime(indicators)

        can_buy = (
            len(candles) >= 30
            and regime in {MarketRegime.TRENDING_UP, MarketRegime.UNCERTAIN}
            and indicators["ema_fast"] > indicators["ema_slow"]
            and 45 <= indicators["rsi"] <= 72
            and indicators["volume_score"] >= 0.35
        )

        stop_distance = max(latest.close * 0.01, latest.close * indicators["atr_pct"] * 1.4)
        take_profit_distance = stop_distance * 2.0

        if can_buy:
            side = SignalSide.BUY
            explanation = (
                "EMA fast is above EMA slow, RSI is not overextended, and volume is acceptable."
            )
        else:
            side = SignalSide.HOLD
            explanation = "No paper entry: trend, RSI, volume, or candle history filter is not satisfied."

        return Signal(
            symbol=symbol,
            side=side,
            confidence=_confidence(indicators, regime),
            entry_price=latest.close,
            stop_loss=max(0.00000001, latest.close - stop_distance),
            take_profit=latest.close + take_profit_distance,
            strategy=self.name,
            market_regime=regime,
            explanation=explanation,
        )


def _confidence(indicators: dict[str, float], regime: MarketRegime) -> float:
    trend_score = min(0.35, abs(indicators["ema_slope"]) * 12)
    rsi_distance = abs(58 - indicators["rsi"])
    rsi_score = max(0.0, 0.25 - (rsi_distance / 100))
    volume_score = min(0.25, indicators["volume_score"] * 0.12)
    regime_score = 0.15 if regime is MarketRegime.TRENDING_UP else 0.05
    return min(0.95, max(0.05, trend_score + rsi_score + volume_score + regime_score))
