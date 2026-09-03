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
    return ema_series(values, period)[-1] if values else 0.0

def ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    if len(values) < period:
        return [sum(values) / len(values)] * len(values)
    
    multiplier = 2 / (period + 1)
    emas = []
    
    # Calculate first EMA (SMA)
    current = sum(values[:period]) / period
    for _ in range(period - 1):
        emas.append(0.0) # Padding
    emas.append(current)
    
    for value in values[period:]:
        current = (value - current) * multiplier + current
        emas.append(current)
    return emas


def rsi_series(values: list[float], period: int = 14) -> list[float]:
    if len(values) <= period:
        return [50.0] * len(values)

    rsis = [50.0] * period
    gains: list[float] = []
    losses: list[float] = []
    
    # Initial averages
    for previous, current in zip(values[:period], values[1:period+1]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
        
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        rsis.append(100.0)
    else:
        rsis.append(100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))))
        
    for previous, current in zip(values[period:len(values)-1], values[period+1:]):
        delta = current - previous
        gain = max(delta, 0.0)
        loss = abs(min(delta, 0.0))
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rsis.append(100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))))
            
    return rsis

def rsi(values: list[float], period: int = 14) -> float:
    return rsi_series(values, period)[-1] if len(values) > period else 50.0

def stoch_rsi(values: list[float], period: int = 14) -> dict[str, float]:
    rsi_vals = rsi_series(values, period)
    if len(rsi_vals) < period:
        return {"k": 50.0, "d": 50.0}
        
    stoch_rsis = []
    for i in range(period, len(rsi_vals) + 1):
        window = rsi_vals[i-period:i]
        min_rsi = min(window)
        max_rsi = max(window)
        if max_rsi == min_rsi:
            stoch_rsis.append(0.0)
        else:
            stoch_rsis.append((rsi_vals[i-1] - min_rsi) / (max_rsi - min_rsi) * 100)
            
    # %K is 3-period SMA of StochRSI
    k_vals = []
    for i in range(3, len(stoch_rsis) + 1):
        k_vals.append(sum(stoch_rsis[i-3:i]) / 3)
        
    # %D is 3-period SMA of %K
    d_vals = []
    for i in range(3, len(k_vals) + 1):
        d_vals.append(sum(k_vals[i-3:i]) / 3)
        
    return {
        "k": k_vals[-1] if k_vals else 50.0,
        "d": d_vals[-1] if d_vals else 50.0
    }

def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float]:
    fast_emas = ema_series(values, fast)
    slow_emas = ema_series(values, slow)
    
    if len(fast_emas) < slow:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
        
    macd_lines = [f - s for f, s in zip(fast_emas[slow-1:], slow_emas[slow-1:])]
    signal_lines = ema_series(macd_lines, signal)
    
    if not signal_lines:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
        
    current_macd = macd_lines[-1]
    current_signal = signal_lines[-1]
    
    return {
        "macd": current_macd,
        "signal": current_signal,
        "hist": current_macd - current_signal
    }


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

    macd_data = macd(closes)
    stoch_data = stoch_rsi(closes)

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
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_hist": macd_data["hist"],
        "stoch_k": stoch_data["k"],
        "stoch_d": stoch_data["d"],
    }
