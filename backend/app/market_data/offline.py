import math

from app.market_data.binance import normalize_symbol, validate_market_request
from app.market_data.schemas import Candle, CandleSeries, MarketOverview, MarketSymbol, MarketTicker


INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

BASE_PRICES = {
    "BTC": 67_500.0,
    "ETH": 3_450.0,
    "BNB": 610.0,
    "SOL": 152.0,
    "XRP": 0.62,
    "ADA": 0.46,
    "AVAX": 32.0,
    "LINK": 14.8,
    "DOGE": 0.13,
    "TRX": 0.12,
    "TON": 5.8,
    "DOT": 6.2,
    "MATIC": 0.72,
    "POL": 0.41,
    "LTC": 78.0,
    "BCH": 430.0,
    "NEAR": 5.1,
    "UNI": 8.9,
    "APT": 7.4,
    "ARB": 0.91,
    "OP": 1.95,
    "ATOM": 7.2,
    "ETC": 28.0,
    "FIL": 5.6,
    "ICP": 11.2,
    "INJ": 25.0,
    "AAVE": 104.0,
    "SUI": 1.15,
    "SEI": 0.43,
    "TIA": 9.6,
    "RENDER": 7.8,
    "FET": 1.55,
    "TAO": 390.0,
    "WLD": 2.8,
    "GRT": 0.26,
    "IMX": 1.75,
    "RUNE": 5.2,
    "ALGO": 0.19,
    "VET": 0.034,
    "FTM": 0.61,
    "GALA": 0.031,
    "SAND": 0.44,
    "MANA": 0.41,
    "AXS": 6.4,
    "APE": 1.2,
    "CHZ": 0.09,
    "CRV": 0.35,
    "MKR": 2_650.0,
    "SNX": 2.4,
    "LDO": 2.0,
    "DYDX": 1.65,
    "JUP": 0.92,
    "PYTH": 0.36,
    "WIF": 2.1,
    "PEPE": 0.000011,
    "SHIB": 0.000018,
    "BONK": 0.000024,
    "FLOKI": 0.00016,
    "JASMY": 0.028,
    "ENA": 0.82,
    "PENDLE": 5.5,
    "ONDO": 1.05,
    "STX": 1.9,
    "KAS": 0.16,
    "XLM": 0.11,
    "HBAR": 0.08,
    "EGLD": 36.0,
    "QNT": 88.0,
    "FLOW": 0.78,
    "KAVA": 0.58,
    "MINA": 0.62,
    "ROSE": 0.09,
    "ZIL": 0.023,
    "1INCH": 0.43,
    "COMP": 52.0,
    "SUSHI": 0.92,
    "ZRX": 0.48,
    "BAT": 0.22,
    "ENJ": 0.25,
    "LRC": 0.21,
    "CELO": 0.63,
    "GMT": 0.18,
    "KSM": 29.0,
    "XTZ": 0.88,
    "EOS": 0.73,
    "IOTA": 0.23,
    "DASH": 31.0,
    "ZEC": 25.0,
    "XMR": 165.0,
}

QUOTE_USD_VALUE = {
    "USDT": 1.0,
    "FDUSD": 1.0,
    "USDC": 1.0,
    "EUR": 1.08,
    "TRY": 0.031,
    "BTC": BASE_PRICES["BTC"],
    "ETH": BASE_PRICES["ETH"],
    "BNB": BASE_PRICES["BNB"],
}

DEFAULT_SYMBOLS = tuple(BASE_PRICES)
DEFAULT_QUOTES = ("USDT", "FDUSD", "USDC", "BTC", "ETH", "BNB", "TRY", "EUR")
INACTIVE_SPOT_BASE_ASSETS_BY_EXCHANGE = {
    "binance": {"XMR"},
    "okx": {"XMR"},
}


def build_offline_candles(
    symbol: str,
    interval: str,
    limit: int = 200,
    exchange: str = "binance",
    cursor: int = 0,
) -> CandleSeries:
    normalized_symbol, normalized_interval, normalized_limit = validate_market_request(
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    base_asset, quote_asset = split_symbol(normalized_symbol)
    if not is_offline_spot_supported(base_asset, exchange):
        raise ValueError(f"{format_symbol_for_exchange(base_asset, quote_asset, exchange)} is not an active paper spot symbol")
    base_price = quote_adjusted_price(base_asset, quote_asset)
    display_symbol = format_symbol_for_exchange(base_asset, quote_asset, exchange)
    profile = market_profile_seed(base_asset, exchange)
    interval_ms = INTERVAL_MS[normalized_interval]
    end_time = 1_735_689_600_000 + interval_ms * cursor
    start_time = end_time - interval_ms * normalized_limit

    candles = []
    for index in range(normalized_limit):
        absolute_index = cursor + index
        open_time = start_time + index * interval_ms
        close = offline_close_price(base_price, absolute_index, profile)
        previous_close = offline_close_price(base_price, max(0, absolute_index - 1), profile)
        open_price = max(0.000001, previous_close)
        high = max(open_price, close) * 1.003
        low = min(open_price, close) * 0.997
        volume = 1_000 + (absolute_index % 24) * 17 + abs(math.sin(absolute_index / 5)) * 250

        candles.append(
            Candle(
                symbol=display_symbol,
                interval=normalized_interval,
                open_time=open_time,
                close_time=open_time + interval_ms - 1,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                quote_volume=volume * close,
                trade_count=500 + absolute_index * 3,
            )
        )

    return CandleSeries(
        symbol=display_symbol,
        interval=normalized_interval,
        source=f"offline_paper_{exchange}_market_data_{quote_asset.lower()}",
        exchange=exchange,
        candles=candles,
    )


def build_offline_symbols(
    quote_asset: str | None = "USDT",
    exchange: str = "binance",
) -> list[MarketSymbol]:
    normalized_quote = quote_asset.upper().strip() if quote_asset else "USDT"
    quotes = [normalized_quote] if normalized_quote in DEFAULT_QUOTES else [normalized_quote]

    symbols = [
        MarketSymbol(
            exchange=exchange,
            symbol=format_symbol_for_exchange(base, quote, exchange),
            base_asset=base,
            quote_asset=quote,
            status="TRADING",
            spot_trading_allowed=True,
        )
        for quote in quotes
        for base in DEFAULT_SYMBOLS
        if base != quote and is_offline_spot_supported(base, exchange)
    ]
    return sorted(symbols, key=lambda item: item.symbol)


def build_offline_tickers(
    quote_asset: str | None = "USDT",
    exchange: str = "binance",
) -> MarketOverview:
    normalized_quote = quote_asset.upper().strip() if quote_asset else "USDT"
    tickers = []

    for index, symbol in enumerate(build_offline_symbols(normalized_quote, exchange=exchange)):
        base_price = quote_adjusted_price(symbol.base_asset, symbol.quote_asset)
        change_pct = round(math.sin(index + 1) * 3.5, 2)
        open_price = base_price / (1 + change_pct / 100)
        last_price = base_price
        high_price = max(open_price, last_price) * 1.018
        low_price = min(open_price, last_price) * 0.982
        volume = 750 + index * 125

        tickers.append(
            MarketTicker(
                exchange=exchange,
                symbol=symbol.symbol,
                price_change=last_price - open_price,
                price_change_percent=change_pct,
                weighted_average_price=(open_price + last_price) / 2,
                last_price=last_price,
                last_quantity=0.1 + index * 0.01,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                quote_volume=volume * last_price,
                trade_count=1_000 + index * 240,
            )
        )

    tickers.sort(key=lambda item: item.quote_volume, reverse=True)
    return MarketOverview(
        source=f"offline_paper_{exchange}_24h_ticker",
        quote_asset=normalized_quote,
        total=len(tickers),
        tickers=tickers,
    )


def split_symbol(symbol: str) -> tuple[str, str]:
    normalized_symbol = normalize_symbol(symbol)
    for quote in sorted(DEFAULT_QUOTES, key=len, reverse=True):
        if normalized_symbol.endswith(quote) and normalized_symbol != quote:
            return normalized_symbol[: -len(quote)], quote
    return normalized_symbol[:-4] or normalized_symbol, normalized_symbol[-4:] or "USDT"


def quote_adjusted_price(base_asset: str, quote_asset: str) -> float:
    base_usd = BASE_PRICES.get(base_asset, 100.0)
    quote_usd = QUOTE_USD_VALUE.get(quote_asset, 1.0)
    if quote_usd <= 0:
        return base_usd
    return base_usd / quote_usd


def is_offline_spot_supported(base_asset: str, exchange: str) -> bool:
    inactive_assets = INACTIVE_SPOT_BASE_ASSETS_BY_EXCHANGE.get(exchange, set())
    return base_asset.upper() not in inactive_assets


def format_symbol_for_exchange(base_asset: str, quote_asset: str, exchange: str) -> str:
    if exchange == "okx":
        return f"{base_asset}-{quote_asset}"
    return f"{base_asset}{quote_asset}"


def market_profile_seed(base_asset: str, exchange: str) -> int:
    return sum(ord(character) for character in f"{exchange}:{base_asset}")


def offline_close_price(base_price: float, index: int, profile: int) -> float:
    phase = (profile % 17) / 3

    if profile % 7 in {0, 3}:
        trend = index * 0.0022
        rhythm = 0.011 if index % 5 in {0, 1, 2} else -0.008
        wave = math.sin(index / 9 + phase) * 0.004
        return max(0.000001, base_price * (1 + trend + rhythm + wave))

    if profile % 7 in {1, 5}:
        trend = index * 0.0002
        wave = math.sin(index / 5 + phase) * 0.024
        return max(0.000001, base_price * (1 + trend + wave))

    if profile % 7 == 2:
        trend = -index * 0.0009
        wave = math.sin(index / 7 + phase) * 0.015
        return max(0.000001, base_price * (1 + trend + wave))

    trend = index * 0.00065
    wave = math.sin(index / 8 + phase) * 0.012
    pulse = math.cos(index / 3 + phase) * 0.004
    return max(0.000001, base_price * (1 + trend + wave + pulse))
