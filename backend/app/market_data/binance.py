from typing import Any

import httpx

from app.market_data.schemas import Candle, CandleSeries, MarketOverview, MarketSymbol, MarketTicker


SUPPORTED_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
}

class MarketDataError(RuntimeError):
    """Raised when public market data cannot be loaded."""

_GLOBAL_SYMBOLS_CACHE: list["MarketSymbol"] | None = None


def normalize_exchange(exchange: str | None) -> str:
    if not exchange:
        return "binance"
    normalized = exchange.strip().lower()
    if normalized in {"okex", "okx"}:
        return "okx"
    if normalized in {"binance", "bnb"}:
        return "binance"
    if normalized in {"all", "combined"}:
        return "all"
    return normalized


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace("-", "").upper().strip()


def validate_market_request(symbol: str, interval: str, limit: int) -> tuple[str, str, int]:
    normalized_symbol = normalize_symbol(symbol)
    normalized_interval = interval.strip()

    if not normalized_symbol.isalnum() or len(normalized_symbol) > 20:
        raise ValueError(f"Invalid symbol: {symbol}")
    if normalized_interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")
    if limit < 1 or limit > 1000:
        raise ValueError("Limit must be between 1 and 1000")

    return normalized_symbol, normalized_interval, limit


def parse_kline(symbol: str, interval: str, row: list[Any]) -> Candle:
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time=int(row[6]),
        quote_volume=float(row[7]),
        trade_count=int(row[8]),
    )


def parse_exchange_symbol(row: dict[str, Any]) -> MarketSymbol:
    return MarketSymbol(
        exchange="binance",
        symbol=str(row["symbol"]),
        base_asset=str(row["baseAsset"]),
        quote_asset=str(row["quoteAsset"]),
        status=str(row["status"]),
        spot_trading_allowed=bool(row.get("isSpotTradingAllowed", False)),
    )


def parse_ticker(row: dict[str, Any]) -> MarketTicker:
    return MarketTicker(
        exchange="binance",
        symbol=str(row["symbol"]),
        price_change=float(row["priceChange"]),
        price_change_percent=float(row["priceChangePercent"]),
        weighted_average_price=float(row["weightedAvgPrice"]),
        last_price=float(row["lastPrice"]),
        last_quantity=float(row["lastQty"]),
        open_price=float(row["openPrice"]),
        high_price=float(row["highPrice"]),
        low_price=float(row["lowPrice"]),
        volume=float(row["volume"]),
        quote_volume=float(row["quoteVolume"]),
        trade_count=int(row["count"]),
    )


class BinanceMarketDataClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_urls = normalize_base_urls(base_url)
        self._timeout = httpx.Timeout(timeout_seconds)

    async def get_candles(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        validate_symbol: bool = True,
    ) -> CandleSeries:
        normalized_symbol, normalized_interval, normalized_limit = validate_market_request(
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        if validate_symbol:
            await self._ensure_active_spot_symbol(normalized_symbol)

        try:
            payload = await self._get_json(
                "/api/v3/klines",
                params={
                    "symbol": normalized_symbol,
                    "interval": normalized_interval,
                    "limit": normalized_limit,
                },
                error_message="Public market data source is unavailable",
            )
        except httpx.HTTPError as exc:
            raise MarketDataError("Public market data source is unavailable") from exc

        if not isinstance(payload, list):
            raise MarketDataError("Unexpected market data payload")

        return CandleSeries(
            symbol=normalized_symbol,
            interval=normalized_interval,
            source="binance_public_market_data",
            exchange="binance",
            candles=[parse_kline(normalized_symbol, normalized_interval, row) for row in payload],
        )

    async def get_symbols(self, quote_asset: str | None = None) -> list[MarketSymbol]:
        symbols = await self._load_symbols()
        normalized_quote = quote_asset.upper().strip() if quote_asset else None
        return [
            symbol
            for symbol in symbols
            if normalized_quote is None or symbol.quote_asset == normalized_quote
        ]

    async def _load_symbols(self) -> list[MarketSymbol]:
        global _GLOBAL_SYMBOLS_CACHE
        if _GLOBAL_SYMBOLS_CACHE is not None:
            return _GLOBAL_SYMBOLS_CACHE

        try:
            payload = await self._get_json(
                "/api/v3/exchangeInfo",
                params=None,
                error_message="Public market symbols source is unavailable",
            )
        except httpx.HTTPError as exc:
            raise MarketDataError("Public market symbols source is unavailable") from exc

        rows = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise MarketDataError("Unexpected market symbols payload")

        symbols = [
            parse_exchange_symbol(row)
            for row in rows
            if isinstance(row, dict)
            and row.get("status") == "TRADING"
            and row.get("isSpotTradingAllowed", False)
        ]
        global _GLOBAL_SYMBOLS_CACHE
        _GLOBAL_SYMBOLS_CACHE = sorted(symbols, key=lambda item: item.symbol)
        return _GLOBAL_SYMBOLS_CACHE

    async def get_24h_tickers(self, quote_asset: str | None = None) -> MarketOverview:
        active_symbols = {symbol.symbol for symbol in await self.get_symbols(quote_asset=quote_asset)}
        try:
            payload = await self._get_json(
                "/api/v3/ticker/24hr",
                params=None,
                error_message="Public market ticker source is unavailable",
            )
        except httpx.HTTPError as exc:
            raise MarketDataError("Public market ticker source is unavailable") from exc

        if not isinstance(payload, list):
            raise MarketDataError("Unexpected market ticker payload")

        normalized_quote = quote_asset.upper().strip() if quote_asset else None
        tickers = [
            parse_ticker(row)
            for row in payload
            if isinstance(row, dict)
            and (normalized_quote is None or str(row.get("symbol", "")).endswith(normalized_quote))
            and str(row.get("symbol", "")) in active_symbols
            and float(row.get("lastPrice", 0) or 0) > 0
            and float(row.get("quoteVolume", 0) or 0) > 0
        ]
        tickers.sort(key=lambda item: item.quote_volume, reverse=True)
        return MarketOverview(
            source="binance_public_24h_ticker",
            quote_asset=normalized_quote,
            total=len(tickers),
            tickers=tickers,
        )

    async def _get_json(
        self,
        path: str,
        params: dict[str, str | int] | None,
        error_message: str,
    ) -> Any:
        last_error: httpx.HTTPError | None = None
        for base_url in self._base_urls:
            try:
                async with httpx.AsyncClient(base_url=base_url, timeout=self._timeout) as client:
                    response = await client.get(path, params=params)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPError as exc:
                last_error = exc

        if last_error is not None:
            raise MarketDataError(error_message) from last_error
        raise MarketDataError(error_message)


    async def _ensure_active_spot_symbol(self, symbol: str) -> None:
        active_symbols = {item.symbol for item in await self._load_symbols()}
        if symbol not in active_symbols:
            raise ValueError(f"{symbol} is not an active Binance spot symbol")


def normalize_base_urls(base_url: str) -> list[str]:
    configured = [url.strip().rstrip("/") for url in base_url.split(",") if url.strip()]
    fallback_urls = [
        "https://data-api.binance.vision",
        "https://api.binance.com",
        "https://api1.binance.com",
        "https://api2.binance.com",
        "https://api3.binance.com",
    ]

    urls: list[str] = []
    for url in [*configured, *fallback_urls]:
        if url and url not in urls:
            urls.append(url)
    return urls
