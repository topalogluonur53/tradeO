from typing import Any

import httpx

from app.market_data.binance import MarketDataError
from app.market_data.schemas import Candle, CandleSeries, MarketOverview, MarketSymbol, MarketTicker


OKX_INTERVALS = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "12h": "12H",
    "1d": "1D",
}


def normalize_okx_symbol(symbol: str) -> str:
    normalized = symbol.replace("/", "-").upper().strip()
    if "-" in normalized:
        return normalized

    for quote in ("USDT", "USDC", "USD", "BTC", "ETH", "EUR", "TRY"):
        if normalized.endswith(quote) and normalized != quote:
            return f"{normalized[:-len(quote)]}-{quote}"
    return normalized


def parse_okx_symbol(row: dict[str, Any]) -> MarketSymbol:
    return MarketSymbol(
        exchange="okx",
        symbol=str(row["instId"]),
        base_asset=str(row["baseCcy"]),
        quote_asset=str(row["quoteCcy"]),
        status=str(row.get("state", "live")).upper(),
        spot_trading_allowed=str(row.get("state", "live")).lower() == "live",
    )


def parse_okx_ticker(row: dict[str, Any]) -> MarketTicker:
    last_price = float(row.get("last") or 0)
    open_price = float(row.get("open24h") or last_price)
    price_change = last_price - open_price
    price_change_percent = (price_change / open_price * 100) if open_price > 0 else 0.0
    high_price = float(row.get("high24h") or last_price)
    low_price = float(row.get("low24h") or last_price)
    volume = float(row.get("vol24h") or 0)
    quote_volume = float(row.get("volCcy24h") or 0)

    return MarketTicker(
        exchange="okx",
        symbol=str(row["instId"]),
        price_change=price_change,
        price_change_percent=price_change_percent,
        weighted_average_price=(open_price + last_price) / 2 if open_price > 0 else last_price,
        last_price=last_price,
        last_quantity=float(row.get("lastSz") or 0),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        volume=volume,
        quote_volume=quote_volume,
        trade_count=0,
    )


def parse_okx_candle(symbol: str, interval: str, row: list[Any]) -> Candle:
    open_time = int(row[0])
    open_price = float(row[1])
    high_price = float(row[2])
    low_price = float(row[3])
    close_price = float(row[4])
    volume = float(row[5])
    quote_volume = float(row[7]) if len(row) > 7 else volume * close_price

    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        close_time=open_time,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        quote_volume=quote_volume,
        trade_count=0,
    )


class OkxMarketDataClient:
    def __init__(self, base_url: str = "https://www.okx.com", timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)

    async def get_candles(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        validate_symbol: bool = True,
    ) -> CandleSeries:
        if interval not in OKX_INTERVALS:
            raise ValueError(f"Unsupported interval: {interval}")
        if limit < 1 or limit > 300:
            raise ValueError("OKX candle limit must be between 1 and 300")

        normalized_symbol = normalize_okx_symbol(symbol)
        if validate_symbol:
            await self._ensure_active_spot_symbol(normalized_symbol)
        payload = await self._get_json(
            "/api/v5/market/candles",
            params={"instId": normalized_symbol, "bar": OKX_INTERVALS[interval], "limit": limit},
            error_message="OKX public market data source is unavailable",
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise MarketDataError("Unexpected OKX candle payload")

        candles = [parse_okx_candle(normalized_symbol, interval, row) for row in reversed(rows)]
        return CandleSeries(
            symbol=normalized_symbol,
            interval=interval,
            source="okx_public_market_data",
            exchange="okx",
            candles=candles,
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
        if hasattr(self, "_symbols_cache"):
            return self._symbols_cache

        payload = await self._get_json(
            "/api/v5/public/instruments",
            params={"instType": "SPOT"},
            error_message="OKX public market symbols source is unavailable",
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise MarketDataError("Unexpected OKX instruments payload")

        symbols = [
            parse_okx_symbol(row)
            for row in rows
            if isinstance(row, dict)
            and str(row.get("state", "live")).lower() == "live"
        ]
        self._symbols_cache = sorted(symbols, key=lambda item: item.symbol)
        return self._symbols_cache

    async def get_24h_tickers(self, quote_asset: str | None = None) -> MarketOverview:
        active_symbols = {symbol.symbol for symbol in await self.get_symbols(quote_asset=quote_asset)}
        payload = await self._get_json(
            "/api/v5/market/tickers",
            params={"instType": "SPOT"},
            error_message="OKX public market ticker source is unavailable",
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise MarketDataError("Unexpected OKX ticker payload")

        normalized_quote = quote_asset.upper().strip() if quote_asset else None
        tickers = [
            parse_okx_ticker(row)
            for row in rows
            if isinstance(row, dict)
            and (normalized_quote is None or str(row.get("instId", "")).endswith(f"-{normalized_quote}"))
            and str(row.get("instId", "")) in active_symbols
            and float(row.get("last") or 0) > 0
            and float(row.get("volCcy24h") or 0) > 0
        ]
        tickers.sort(key=lambda item: item.quote_volume, reverse=True)
        return MarketOverview(
            source="okx_public_24h_ticker",
            quote_asset=normalized_quote,
            total=len(tickers),
            tickers=tickers,
        )

    async def _get_json(
        self,
        path: str,
        params: dict[str, str | int],
        error_message: str,
    ) -> Any:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.get(path, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise MarketDataError(error_message) from exc

    async def _ensure_active_spot_symbol(self, symbol: str) -> None:
        active_symbols = {item.symbol for item in await self._load_symbols()}
        if symbol not in active_symbols:
            raise ValueError(f"{symbol} is not an active OKX spot symbol")
