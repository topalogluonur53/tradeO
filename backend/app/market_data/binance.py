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
        symbol=str(row["symbol"]),
        base_asset=str(row["baseAsset"]),
        quote_asset=str(row["quoteAsset"]),
        status=str(row["status"]),
        spot_trading_allowed=bool(row.get("isSpotTradingAllowed", False)),
    )


def parse_ticker(row: dict[str, Any]) -> MarketTicker:
    return MarketTicker(
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
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)

    async def get_candles(self, symbol: str, interval: str, limit: int = 200) -> CandleSeries:
        normalized_symbol, normalized_interval, normalized_limit = validate_market_request(
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.get(
                    "/api/v3/klines",
                    params={
                        "symbol": normalized_symbol,
                        "interval": normalized_interval,
                        "limit": normalized_limit,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError("Public market data source is unavailable") from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise MarketDataError("Unexpected market data payload")

        return CandleSeries(
            symbol=normalized_symbol,
            interval=normalized_interval,
            source="binance_public_market_data",
            candles=[parse_kline(normalized_symbol, normalized_interval, row) for row in payload],
        )

    async def get_symbols(self, quote_asset: str | None = None) -> list[MarketSymbol]:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.get("/api/v3/exchangeInfo")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError("Public market symbols source is unavailable") from exc

        payload = response.json()
        rows = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise MarketDataError("Unexpected market symbols payload")

        normalized_quote = quote_asset.upper().strip() if quote_asset else None
        symbols = [
            parse_exchange_symbol(row)
            for row in rows
            if isinstance(row, dict)
            and row.get("status") == "TRADING"
            and row.get("isSpotTradingAllowed", False)
            and (normalized_quote is None or row.get("quoteAsset") == normalized_quote)
        ]
        return sorted(symbols, key=lambda item: item.symbol)

    async def get_24h_tickers(self, quote_asset: str | None = None) -> MarketOverview:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.get("/api/v3/ticker/24hr")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError("Public market ticker source is unavailable") from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise MarketDataError("Unexpected market ticker payload")

        normalized_quote = quote_asset.upper().strip() if quote_asset else None
        tickers = [
            parse_ticker(row)
            for row in payload
            if isinstance(row, dict)
            and (normalized_quote is None or str(row.get("symbol", "")).endswith(normalized_quote))
        ]
        tickers.sort(key=lambda item: item.quote_volume, reverse=True)
        return MarketOverview(
            source="binance_public_24h_ticker",
            quote_asset=normalized_quote,
            total=len(tickers),
            tickers=tickers,
        )
