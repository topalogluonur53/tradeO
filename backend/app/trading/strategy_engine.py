from app.market_data.schemas import Candle
from app.trading.indicators import calculate_indicator_snapshot
from app.trading.regime import detect_market_regime
from app.trading.schemas import MarketRegime, Signal, SignalFilter, SignalSide


class NexusAIStrategy:
    name = "NEXUS_AI_TREND_SQUEEZE"

    def __init__(
        self, 
        bollinger_width: float = 0.08, 
        rsi_min: float = 35.0, 
        rsi_max: float = 70.0, 
        volume_multiplier: float = 0.6
    ):
        self.bollinger_width = bollinger_width
        self.rsi_min = rsi_min
        self.rsi_max = rsi_max
        self.volume_multiplier = volume_multiplier

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
                label="Geniş Trend",
                passed=indicators["ema_fast"] > indicators["ema_slow"],
                actual=f"{indicators['ema_fast']:.6g} / {indicators['ema_slow']:.6g}",
                required="EMA fast > EMA slow",
            ),
            SignalFilter(
                key="bb_squeeze",
                label="Volatilite Sıkışması",
                passed=indicators["bb_bandwidth"] < self.bollinger_width,
                actual=f"{indicators['bb_bandwidth'] * 100:.2f}%",
                required=f"< {self.bollinger_width * 100:.1f}% (Sıkışma)",
            ),
            SignalFilter(
                key="rsi",
                label="RSI Soğuması",
                passed=self.rsi_min <= indicators["rsi"] <= self.rsi_max,
                actual=f"{indicators['rsi']:.2f}",
                required=f"{self.rsi_min} - {self.rsi_max}",
            ),
            SignalFilter(
                key="volume",
                label="Hacim Teyidi",
                passed=indicators["volume_score"] >= self.volume_multiplier,
                actual=f"{indicators['volume_score']:.2f}",
                required=f">= {self.volume_multiplier}x ort.",
            ),
        ]
        can_buy = all(item.passed for item in filters)

        stop_distance = max(latest.close * 0.01, latest.close * indicators["atr_pct"] * 1.5)
        take_profit_distance = stop_distance * 2.5

        if can_buy:
            side = SignalSide.BUY
            explanation = (
                "Nexus Yapay Zeka: Fiyat Bollinger bantlarında sıkışma sonrası güçlü hacimle kırılıma hazır. EMA yükseliş trendinde."
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
    trend_score = min(0.35, abs(indicators["ema_slope"]) * 15)
    rsi_distance = abs(55 - indicators["rsi"])
    rsi_score = max(0.0, 0.20 - (rsi_distance / 120))
    
    # High volume breaking out of a tight squeeze increases confidence massively
    squeeze_bonus = 0.20 if indicators.get("bb_bandwidth", 1.0) < 0.04 else 0.0
    volume_score = min(0.20, indicators["volume_score"] * 0.1)
    
    regime_score = 0.15 if regime is MarketRegime.TRENDING_UP else 0.05
    return min(0.95, max(0.05, trend_score + rsi_score + volume_score + squeeze_bonus + regime_score))
