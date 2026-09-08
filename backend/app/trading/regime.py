from app.trading.schemas import MarketRegime


def detect_market_regime(indicators: dict[str, float]) -> MarketRegime:
    atr_pct = indicators.get("atr_pct", 0.0)
    volume_score = indicators.get("volume_score", 1.0)
    ema_slope = indicators.get("ema_slope", 0.0)
    adx = indicators.get("adx", 0.0)
    plus_di = indicators.get("plus_di", 0.0)
    minus_di = indicators.get("minus_di", 0.0)

    if volume_score < 0.25:
        return MarketRegime.LOW_LIQUIDITY
    if atr_pct > 0.06:
        return MarketRegime.HIGH_VOLATILITY
    if adx >= 20.0 and plus_di > minus_di and ema_slope > 0:
        return MarketRegime.TRENDING_UP
    if adx >= 20.0 and minus_di > plus_di and ema_slope < 0:
        return MarketRegime.TRENDING_DOWN
    if adx < 18.0 or atr_pct < 0.01:
        return MarketRegime.RANGING
    return MarketRegime.UNCERTAIN
