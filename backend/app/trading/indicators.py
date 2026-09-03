from app.market_data.schemas import Candle
import math

def sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    return sum(values[-period:]) / period

def standard_deviation(values: list[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    slice_vals = values[-period:]
    mean = sum(slice_vals) / period
    variance = sum((x - mean) ** 2 for x in slice_vals) / period
    return math.sqrt(variance)
def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)

    multiplier = 2 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0

    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0

    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def atr_pct(candles: list[Candle], period: int = 14) -> float:
    if len(candles) <= period:
        return 0.0

    true_ranges: list[float] = []
    selected = candles[-period:]
    previous_close = candles[-period - 1].close
    for candle in selected:
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        )
        true_ranges.append(true_range)
        previous_close = candle.close

    latest_close = candles[-1].close
    if latest_close <= 0:
        return 0.0
    return (sum(true_ranges) / period) / latest_close


def volume_score(candles: list[Candle], period: int = 20) -> float:
    if len(candles) < period + 1:
        return 1.0

    average_volume = sum(candle.volume for candle in candles[-period - 1 : -1]) / period
    if average_volume <= 0:
        return 0.0
    return min(2.0, candles[-1].volume / average_volume)


def calculate_indicator_snapshot(candles: list[Candle]) -> dict[str, float]:
    closes = [candle.close for candle in candles]
    ema_fast = ema(closes, 12)
    ema_slow = ema(closes, 26)
    latest_close = closes[-1] if closes else 0.0
    ema_slope = 0.0 if latest_close <= 0 else (ema_fast - ema_slow) / latest_close

    bb_middle = sma(closes, 20)
    bb_std = standard_deviation(closes, 20)
    bb_upper = bb_middle + (2.0 * bb_std)
    bb_lower = bb_middle - (2.0 * bb_std)
    
    # Calculate squeeze (bandwidth)
    bb_bandwidth = (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0.0
    
    # Calculate where the price is relative to the bands (0 = lower, 1 = upper)
    bb_percent = (latest_close - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

    return {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "ema_slope": ema_slope,
        "rsi": rsi(closes),
        "atr_pct": atr_pct(candles),
        "volume_score": volume_score(candles),
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_bandwidth": bb_bandwidth,
        "bb_percent": bb_percent,
    }
