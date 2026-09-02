from app.trading.schemas import MarketRegime


def detect_market_regime(indicators: dict[str, float]) -> MarketRegime:
    atr_pct = indicators.get("atr_pct", 0.0)
    volume_score = indicators.get("volume_score", 1.0)
    ema_slope = indicators.get("ema_slope", 0.0)

    if volume_score < 0.25:
        return MarketRegime.LOW_LIQUIDITY
    if atr_pct > 0.06:
        return MarketRegime.HIGH_VOLATILITY
    if ema_slope > 0.01:
        return MarketRegime.TRENDING_UP
    if ema_slope < -0.01:
        return MarketRegime.TRENDING_DOWN
    if atr_pct < 0.015:
        return MarketRegime.RANGING
    return MarketRegime.UNCERTAIN
