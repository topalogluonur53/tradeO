from app.market_data.schemas import Candle
from app.trading.schemas import PatternDirection, PricePattern


def detect_price_patterns(candles: list[Candle]) -> list[PricePattern]:
    """Detect a compact set of objective, high-signal price formations."""
    if len(candles) < 3:
        return []

    patterns: list[PricePattern] = []
    previous, latest = candles[-2], candles[-1]

    if _bullish_engulfing(previous, latest):
        patterns.append(_pattern("bullish_engulfing", "Boğa Yutan", "BULLISH", 0.78))
    if _bearish_engulfing(previous, latest):
        patterns.append(_pattern("bearish_engulfing", "Ayı Yutan", "BEARISH", 0.82))
    if _hammer(latest) and _declining_context(candles):
        patterns.append(_pattern("hammer", "Çekiç", "BULLISH", 0.68))
    if _shooting_star(latest) and _rising_context(candles):
        patterns.append(_pattern("shooting_star", "Kayan Yıldız", "BEARISH", 0.72))
    if _morning_star(candles[-3:]):
        patterns.append(_pattern("morning_star", "Sabah Yıldızı", "BULLISH", 0.86))
    if _evening_star(candles[-3:]):
        patterns.append(_pattern("evening_star", "Akşam Yıldızı", "BEARISH", 0.88))
    if _three_white_soldiers(candles[-3:]):
        patterns.append(_pattern("three_white_soldiers", "Üç Beyaz Asker", "BULLISH", 0.82))
    if _three_black_crows(candles[-3:]):
        patterns.append(_pattern("three_black_crows", "Üç Siyah Karga", "BEARISH", 0.88))

    if len(candles) >= 21:
        prior = candles[-21:-1]
        if latest.close > max(candle.high for candle in prior):
            patterns.append(_pattern("range_breakout", "20 Mum Direnç Kırılımı", "BULLISH", 0.90))
        if latest.close < min(candle.low for candle in prior):
            patterns.append(_pattern("range_breakdown", "20 Mum Destek Kırılımı", "BEARISH", 0.94))

    if len(candles) >= 35:
        double_pattern = _double_top_or_bottom(candles[-35:])
        if double_pattern is not None:
            patterns.append(double_pattern)

    return patterns


def pattern_strength(
    patterns: list[PricePattern],
    direction: PatternDirection,
) -> float:
    return max(
        (pattern.strength for pattern in patterns if pattern.direction is direction),
        default=0.0,
    )


def _pattern(
    key: str,
    label: str,
    direction: PatternDirection,
    strength: float,
) -> PricePattern:
    return PricePattern(key=key, label=label, direction=direction, strength=strength)


def _body(candle: Candle) -> float:
    return abs(candle.close - candle.open)


def _range(candle: Candle) -> float:
    return max(candle.high - candle.low, 1e-12)


def _bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def _bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def _bullish_engulfing(previous: Candle, latest: Candle) -> bool:
    return (
        _bearish(previous)
        and _bullish(latest)
        and latest.open <= previous.close
        and latest.close >= previous.open
        and _body(latest) >= _body(previous) * 1.05
    )


def _bearish_engulfing(previous: Candle, latest: Candle) -> bool:
    return (
        _bullish(previous)
        and _bearish(latest)
        and latest.open >= previous.close
        and latest.close <= previous.open
        and _body(latest) >= _body(previous) * 1.05
    )


def _hammer(candle: Candle) -> bool:
    body = max(_body(candle), _range(candle) * 0.05)
    lower_shadow = min(candle.open, candle.close) - candle.low
    upper_shadow = candle.high - max(candle.open, candle.close)
    return lower_shadow >= body * 2.0 and upper_shadow <= body * 0.75


def _shooting_star(candle: Candle) -> bool:
    body = max(_body(candle), _range(candle) * 0.05)
    upper_shadow = candle.high - max(candle.open, candle.close)
    lower_shadow = min(candle.open, candle.close) - candle.low
    return upper_shadow >= body * 2.0 and lower_shadow <= body * 0.75


def _morning_star(candles: list[Candle]) -> bool:
    first, middle, latest = candles
    return (
        _bearish(first)
        and _body(first) >= _range(first) * 0.50
        and _body(middle) <= _body(first) * 0.45
        and _bullish(latest)
        and latest.close >= (first.open + first.close) / 2
    )


def _evening_star(candles: list[Candle]) -> bool:
    first, middle, latest = candles
    return (
        _bullish(first)
        and _body(first) >= _range(first) * 0.50
        and _body(middle) <= _body(first) * 0.45
        and _bearish(latest)
        and latest.close <= (first.open + first.close) / 2
    )


def _three_white_soldiers(candles: list[Candle]) -> bool:
    return (
        all(_bullish(candle) and _body(candle) >= _range(candle) * 0.45 for candle in candles)
        and candles[0].close < candles[1].close < candles[2].close
        and candles[0].open <= candles[1].open <= candles[0].close
        and candles[1].open <= candles[2].open <= candles[1].close
    )


def _three_black_crows(candles: list[Candle]) -> bool:
    return (
        all(_bearish(candle) and _body(candle) >= _range(candle) * 0.45 for candle in candles)
        and candles[0].close > candles[1].close > candles[2].close
        and candles[0].close <= candles[1].open <= candles[0].open
        and candles[1].close <= candles[2].open <= candles[1].open
    )


def _declining_context(candles: list[Candle]) -> bool:
    context = candles[-6:-1]
    return len(context) >= 3 and context[-1].close < context[0].close


def _rising_context(candles: list[Candle]) -> bool:
    context = candles[-6:-1]
    return len(context) >= 3 and context[-1].close > context[0].close


def _local_extrema(candles: list[Candle], use_high: bool) -> list[tuple[int, float]]:
    values = [candle.high if use_high else candle.low for candle in candles]
    result: list[tuple[int, float]] = []
    for index in range(2, len(values) - 2):
        window = values[index - 2 : index + 3]
        value = values[index]
        if (use_high and value == max(window)) or (not use_high and value == min(window)):
            result.append((index, value))
    return result


def _double_top_or_bottom(candles: list[Candle]) -> PricePattern | None:
    latest_close = candles[-1].close
    lows = _local_extrema(candles[:-1], use_high=False)
    if len(lows) >= 2:
        (first_index, first_low), (second_index, second_low) = lows[-2:]
        separation = second_index - first_index
        tolerance = abs(first_low - second_low) / max(first_low, second_low)
        if 4 <= separation <= 24 and tolerance <= 0.025:
            neckline = max(candle.high for candle in candles[first_index : second_index + 1])
            if latest_close > neckline:
                return _pattern("double_bottom", "İkili Dip Kırılımı", "BULLISH", 0.92)

    highs = _local_extrema(candles[:-1], use_high=True)
    if len(highs) >= 2:
        (first_index, first_high), (second_index, second_high) = highs[-2:]
        separation = second_index - first_index
        tolerance = abs(first_high - second_high) / max(first_high, second_high)
        if 4 <= separation <= 24 and tolerance <= 0.025:
            neckline = min(candle.low for candle in candles[first_index : second_index + 1])
            if latest_close < neckline:
                return _pattern("double_top", "İkili Tepe Kırılımı", "BEARISH", 0.94)
    return None
