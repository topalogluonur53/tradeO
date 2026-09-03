from app.market_data.schemas import Candle
from app.trading.indicators import calculate_indicator_snapshot
from app.trading.regime import detect_market_regime
from app.trading.schemas import MarketRegime, Signal, SignalFilter, SignalSide


class EmaRsiStrategy:
    name = "EMA_RSI_SPOT_LONG"

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal:
        latest = candles[-1]
        indicators = calculate_indicator_snapshot(candles)
        regime = detect_market_regime(indicators)

        filters = [
            SignalFilter(
                key="history",
                label="Mum geçmişi",
                passed=len(candles) >= 30,
                actual=str(len(candles)),
                required=">= 30",
            ),
            SignalFilter(
                key="regime",
                label="Piyasa rejimi",
                passed=regime in {MarketRegime.TRENDING_UP, MarketRegime.UNCERTAIN},
                actual=regime.value,
                required="TRENDING_UP veya UNCERTAIN",
            ),
            SignalFilter(
                key="ema_trend",
                label="EMA trend",
                passed=indicators["ema_fast"] > indicators["ema_slow"],
                actual=f"{indicators['ema_fast']:.6g} / {indicators['ema_slow']:.6g}",
                required="EMA fast > EMA slow",
            ),
            SignalFilter(
                key="rsi",
                label="RSI aralığı",
                passed=45 <= indicators["rsi"] <= 72,
                actual=f"{indicators['rsi']:.2f}",
                required="45 - 72",
            ),
            SignalFilter(
                key="volume",
                label="Hacim skoru",
                passed=indicators["volume_score"] >= 0.35,
                actual=f"{indicators['volume_score']:.2f}",
                required=">= 0.35",
            ),
        ]
        can_buy = all(item.passed for item in filters)

        stop_distance = max(latest.close * 0.01, latest.close * indicators["atr_pct"] * 1.4)
        take_profit_distance = stop_distance * 2.0

        if can_buy:
            side = SignalSide.BUY
            explanation = (
                "Paper giriş uygun: hızlı EMA yavaş EMA üzerinde, RSI aşırı bölgede değil ve hacim kabul edilebilir."
            )
        else:
            side = SignalSide.HOLD
            failed_filters = ", ".join(item.label for item in filters if not item.passed)
            explanation = f"Paper giriş yok: {failed_filters} filtresi sağlanmadı."

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
            indicators={key: round(value, 8) for key, value in indicators.items()},
            filters=filters,
        )


def _confidence(indicators: dict[str, float], regime: MarketRegime) -> float:
    trend_score = min(0.35, abs(indicators["ema_slope"]) * 12)
    rsi_distance = abs(58 - indicators["rsi"])
    rsi_score = max(0.0, 0.25 - (rsi_distance / 100))
    volume_score = min(0.25, indicators["volume_score"] * 0.12)
    regime_score = 0.15 if regime is MarketRegime.TRENDING_UP else 0.05
    return min(0.95, max(0.05, trend_score + rsi_score + volume_score + regime_score))
