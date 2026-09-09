from datetime import UTC, datetime

from app.market_data.schemas import Candle
from app.trading.indicators import aggregate_candles, calculate_indicator_snapshot
from app.trading.patterns import detect_price_patterns, pattern_strength
from app.trading.regime import detect_market_regime
from app.trading.schemas import (
    MarketRegime,
    PatternDirection,
    PricePattern,
    Signal,
    SignalFilter,
    SignalSide,
)


class NexusAIStrategy:
    name = "NEXUS_CONFLUENCE_V2"

    def __init__(
        self,
        bollinger_width: float = 0.15,
        rsi_min: float = 25.0,
        rsi_max: float = 78.0,
        volume_multiplier: float = 0.8,
        macd_enabled: bool = False,
        stoch_enabled: bool = False,
        mtf_enabled: bool = False,
        minimum_score: float = 0.60,
    ) -> None:
        self.bollinger_width = bollinger_width
        self.rsi_min = rsi_min
        self.rsi_max = rsi_max
        self.volume_multiplier = volume_multiplier
        self.macd_enabled = macd_enabled
        self.stoch_enabled = stoch_enabled
        self.mtf_enabled = mtf_enabled
        self.minimum_score = minimum_score

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal:
        if not candles:
            raise ValueError("At least one candle is required")

        latest = candles[-1]
        indicators = calculate_indicator_snapshot(candles)
        regime = detect_market_regime(indicators)
        patterns = detect_price_patterns(candles)
        bullish_strength = pattern_strength(patterns, PatternDirection.BULLISH)
        bearish_strength = pattern_strength(patterns, PatternDirection.BEARISH)

        history_ok = len(candles) >= 30
        safe_regime = regime not in {
            MarketRegime.TRENDING_DOWN,
            MarketRegime.HIGH_VOLATILITY,
            MarketRegime.LOW_LIQUIDITY,
        }
        ema_trend = indicators["ema_fast"] > indicators["ema_slow"]
        price_confirmation = (
            latest.close > indicators["ema_fast"] and indicators["bb_percent"] >= 0.50
        )
        rsi_ok = self.rsi_min <= indicators["rsi"] <= self.rsi_max
        volume_ok = indicators["volume_score"] >= self.volume_multiplier
        directional_ok = (
            indicators["plus_di"] >= indicators["minus_di"] or bullish_strength >= 0.80
        )
        trend_strength_ok = (
            indicators["adx"] >= 18 and directional_ok
        ) or bullish_strength >= 0.85
        squeeze = indicators["bb_bandwidth"] < self.bollinger_width
        breakout = any(
            pattern.key in {"range_breakout", "double_bottom"} for pattern in patterns
        )
        bearish_break = any(
            pattern.key in {"range_breakdown", "double_top"} for pattern in patterns
        )
        bullish_confirmation = (
            latest.close > latest.open
            and (len(candles) < 2 or latest.close > candles[-2].close)
        )
        pullback = (
            ema_trend
            and latest.low <= indicators["ema_fast"] * 1.005
            and latest.close > indicators["ema_fast"]
            and bullish_confirmation
        )
        reversal_setup = bullish_strength >= 0.68 and latest.close > indicators["ema_slow"]
        trend_setup = ema_trend and price_confirmation and (
            (squeeze and bullish_confirmation) or pullback or breakout
        )
        setup_ok = trend_setup or reversal_setup
        bearish_veto = bearish_strength >= 0.75
        trend_reversal = (
            indicators["ema_fast"] < indicators["ema_slow"]
            and indicators["minus_di"] > indicators["plus_di"]
            and indicators["macd_hist"] < 0
        )
        # Spot-long portfolios cannot profit from a broad decline.  Waiting
        # for every slow reversal indicator to agree gives a sell-off too much
        # room, so an established downtrend is an unconditional risk-off
        # signal.  The momentum branch catches deterioration before ADX has
        # had enough time to classify it as a full downtrend.
        downtrend_exit = regime is MarketRegime.TRENDING_DOWN
        momentum_exit = (
            latest.close < indicators["ema_fast"]
            and indicators["minus_di"] > indicators["plus_di"]
            and indicators["macd_hist"] < 0
            and (indicators["rsi"] < 45 or latest.close < indicators["ema_slow"])
        )
        volatility_exit = (
            regime is MarketRegime.HIGH_VOLATILITY
            and latest.close < indicators["ema_slow"]
            and indicators["minus_di"] > indicators["plus_di"]
        )

        mtf_ok, mtf_actual = self._higher_timeframe_confirmation(candles)
        macd_ok = indicators["macd_hist"] > 0
        stoch_ok = indicators["stoch_k"] > indicators["stoch_d"] and indicators["stoch_k"] < 80

        score = _confluence_score(
            indicators=indicators,
            regime=regime,
            bullish_strength=bullish_strength,
            bearish_strength=bearish_strength,
            squeeze=squeeze,
            breakout=breakout,
            pullback=pullback,
            rsi_ok=rsi_ok,
            volume_ok=volume_ok,
            mtf_ok=mtf_ok if self.mtf_enabled else None,
        )

        filters = [
            _filter("history", "Mum geçmişi", history_ok, str(len(candles)), ">= 30"),
            _filter(
                "regime",
                "Piyasa rejimi",
                safe_regime,
                regime.value,
                "Düşüş, aşırı volatilite veya düşük likidite olmamalı",
            ),
            _filter(
                "ema_trend",
                "Ana trend",
                ema_trend,
                f"{indicators['ema_fast']:.6g} / {indicators['ema_slow']:.6g}",
                "EMA fast > EMA slow",
            ),
            _filter(
                "price_confirmation",
                "Fiyat teyidi",
                price_confirmation,
                f"BB %{indicators['bb_percent'] * 100:.1f}",
                "Fiyat EMA fast ve Bollinger orta bandı üzerinde",
            ),
            _filter(
                "adx_direction",
                "ADX trend gücü",
                trend_strength_ok,
                (
                    f"ADX {indicators['adx']:.1f} / +DI {indicators['plus_di']:.1f} / "
                    f"-DI {indicators['minus_di']:.1f}"
                ),
                "ADX >= 18 ve yön yukarı",
            ),
            _filter(
                "setup",
                "Akıllı kurulum",
                setup_ok,
                _setup_name(breakout, pullback, reversal_setup, squeeze),
                "Trend devamı, kırılım, pullback veya güçlü dönüş",
            ),
            _filter(
                "rsi",
                "RSI dengesi",
                rsi_ok,
                f"{indicators['rsi']:.2f}",
                f"{self.rsi_min} - {self.rsi_max}",
            ),
            _filter(
                "volume",
                "Hacim teyidi",
                volume_ok,
                f"{indicators['volume_score']:.2f}x",
                f">= {self.volume_multiplier}x ortalama",
            ),
            _filter(
                "formation",
                "Formasyon dengesi",
                bullish_strength > bearish_strength,
                _pattern_summary(patterns),
                "Boğa formasyonu ayı formasyonundan güçlü olmalı",
            ),
            _filter(
                "bearish_veto",
                "Ayı veto filtresi",
                not bearish_veto,
                f"{bearish_strength:.0%}",
                "Güçlü ayı dönüşü bulunmamalı",
            ),
            _filter(
                "confluence",
                "Birleşik analiz skoru",
                score >= self.minimum_score,
                f"{score:.0%}",
                f">= {self.minimum_score:.0%}",
            ),
        ]

        if self.macd_enabled:
            filters.append(
                _filter(
                    "macd",
                    "MACD momentum",
                    macd_ok,
                    f"{indicators['macd_hist']:.6g}",
                    "> 0",
                )
            )
        if self.stoch_enabled:
            filters.append(
                _filter(
                    "stoch_rsi",
                    "Stoch RSI dönüşü",
                    stoch_ok,
                    f"K {indicators['stoch_k']:.1f} / D {indicators['stoch_d']:.1f}",
                    "K > D ve K < 80",
                )
            )
        if self.mtf_enabled:
            filters.append(
                _filter(
                    "mtf",
                    "Üst zaman trendi",
                    mtf_ok,
                    mtf_actual,
                    "4x zaman diliminde EMA ve yön yukarı",
                )
            )

        mandatory = [history_ok, safe_regime, setup_ok, rsi_ok, volume_ok, trend_strength_ok]
        optional_gates = [
            not bearish_veto,
            score >= self.minimum_score,
            not self.macd_enabled or macd_ok,
            not self.stoch_enabled or stoch_ok,
            not self.mtf_enabled or mtf_ok,
        ]
        can_buy = all([*mandatory, *optional_gates])

        stop_distance = _smart_stop_distance(latest, candles, indicators, patterns)
        take_profit_distance = stop_distance * 2.5
        risk_off_exit = downtrend_exit or momentum_exit or volatility_exit
        should_sell = bearish_veto or bearish_break or trend_reversal or risk_off_exit
        if should_sell:
            side = SignalSide.SELL
            sell_strength = min(
                0.95,
                max(
                    bearish_strength,
                    0.88 if downtrend_exit else 0.0,
                    0.80 if volatility_exit else 0.0,
                    0.74 if momentum_exit else 0.0,
                    0.78 if bearish_break else 0.0,
                    0.72 if trend_reversal else 0.0,
                ),
            )
            confidence = sell_strength
            if downtrend_exit:
                exit_detail = "teyitli düşüş rejimi"
            elif volatility_exit:
                exit_detail = "aşağı yönlü yüksek volatilite"
            elif momentum_exit:
                exit_detail = "aşağı momentum kırılması"
            elif trend_reversal:
                exit_detail = "trend ve momentum aşağı döndü"
            else:
                exit_detail = _pattern_summary(patterns)
            explanation = f"Çıkış sinyali ({sell_strength:.0%}): {exit_detail}."
        elif can_buy:
            side = SignalSide.BUY
            confidence = score
            explanation = (
                f"Güçlü {_setup_name(breakout, pullback, reversal_setup, squeeze)} kurulumu: "
                f"birleşik skor {score:.0%}. {_pattern_summary(patterns)}"
            )
        else:
            side = SignalSide.HOLD
            confidence = score
            failed = ", ".join(
                item.label
                for item in filters
                if not item.passed and item.key != "formation"
            )
            explanation = f"Giriş beklemede ({score:.0%}): {failed or 'teyit yetersiz'}."

        return Signal(
            symbol=symbol,
            side=side,
            confidence=confidence,
            entry_price=latest.close,
            stop_loss=max(0.00000001, latest.close - stop_distance),
            take_profit=latest.close + take_profit_distance,
            strategy=self.name,
            market_regime=regime,
            timestamp=datetime.fromtimestamp(latest.close_time / 1000, tz=UTC),
            explanation=explanation,
            indicators={key: round(value, 8) for key, value in indicators.items()},
            filters=filters,
            patterns=patterns,
        )

    def _higher_timeframe_confirmation(self, candles: list[Candle]) -> tuple[bool, str]:
        higher_timeframe = aggregate_candles(candles, factor=4)
        if len(higher_timeframe) < 26:
            return False, f"Yetersiz üst zaman verisi ({len(higher_timeframe)}/26)"
        snapshot = calculate_indicator_snapshot(higher_timeframe)
        passed = (
            snapshot["ema_fast"] > snapshot["ema_slow"]
            and snapshot["plus_di"] >= snapshot["minus_di"]
        )
        return (
            passed,
            (
                f"EMA {snapshot['ema_fast']:.6g}/{snapshot['ema_slow']:.6g}, "
                f"ADX {snapshot['adx']:.1f}"
            ),
        )


EmaRsiStrategy = NexusAIStrategy


def _filter(
    key: str,
    label: str,
    passed: bool,
    actual: str,
    required: str,
) -> SignalFilter:
    return SignalFilter(
        key=key,
        label=label,
        passed=passed,
        actual=actual,
        required=required,
    )


def _confluence_score(
    indicators: dict[str, float],
    regime: MarketRegime,
    bullish_strength: float,
    bearish_strength: float,
    squeeze: bool,
    breakout: bool,
    pullback: bool,
    rsi_ok: bool,
    volume_ok: bool,
    mtf_ok: bool | None,
) -> float:
    score = 0.0
    score += 0.14 if regime is MarketRegime.TRENDING_UP else 0.07 if regime is MarketRegime.UNCERTAIN else 0.03
    score += 0.16 if indicators["ema_fast"] > indicators["ema_slow"] else 0.0
    score += 0.12 if indicators["bb_percent"] >= 0.50 else 0.0
    score += 0.10 if rsi_ok else 0.0
    score += 0.10 if volume_ok else 0.0
    score += 0.12 if indicators["adx"] >= 18 and indicators["plus_di"] >= indicators["minus_di"] else 0.0
    score += 0.08 if indicators["macd_hist"] > 0 else 0.0
    score += 0.04 if indicators["stoch_k"] > indicators["stoch_d"] else 0.0
    score += 0.04 if squeeze else 0.0
    score += 0.12 if breakout else 0.0
    score += 0.08 if pullback else 0.0
    score += bullish_strength * 0.18
    score -= bearish_strength * 0.28
    if mtf_ok is True:
        score += 0.10
    elif mtf_ok is False:
        score -= 0.10
    return min(0.95, max(0.05, score))


def _smart_stop_distance(
    latest: Candle,
    candles: list[Candle],
    indicators: dict[str, float],
    patterns: list[PricePattern],
) -> float:
    atr_distance = latest.close * indicators["atr_pct"] * 1.5
    base_distance = max(latest.close * 0.01, atr_distance)
    if not any(pattern.direction is PatternDirection.BULLISH for pattern in patterns):
        return base_distance

    structure_low = min(candle.low for candle in candles[-5:])
    structure_distance = latest.close - structure_low + (atr_distance * 0.10)
    if 0 < structure_distance <= latest.close * 0.05:
        return max(base_distance, structure_distance)
    return base_distance


def _setup_name(
    breakout: bool,
    pullback: bool,
    reversal: bool,
    squeeze: bool,
) -> str:
    if breakout:
        return "kırılım"
    if reversal:
        return "formasyon dönüşü"
    if pullback:
        return "trend pullback"
    if squeeze:
        return "sıkışma devamı"
    return "trend devamı"


def _pattern_summary(patterns: list[PricePattern]) -> str:
    if not patterns:
        return "Belirgin formasyon yok"
    return ", ".join(
        f"{pattern.label} ({pattern.direction.value.lower()}, {pattern.strength:.0%})"
        for pattern in patterns
    )
