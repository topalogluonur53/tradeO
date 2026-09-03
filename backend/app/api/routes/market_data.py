from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.auth import get_current_user
from app.models.user import User
from app.core.config import Settings, get_settings
from app.market_data.binance import BinanceMarketDataClient, MarketDataError, normalize_exchange
from app.market_data.offline import build_offline_candles, build_offline_symbols, build_offline_tickers
from app.market_data.okx import OkxMarketDataClient
from app.market_data.schemas import CandleSeries, MarketOverview, MarketSymbol

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/candles", response_model=CandleSeries)
async def get_candles(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    limit: int = Query(default=200, ge=1, le=1000),
    exchange: str = Query(default="binance", min_length=2, max_length=12),
    current_user: User = Depends(get_current_user)
) -> CandleSeries:
    settings = get_settings()
    selected_exchange = normalize_exchange(exchange)
    if selected_exchange == "all":
        selected_exchange = "binance"

    try:
        if selected_exchange == "okx":
            client = OkxMarketDataClient(timeout_seconds=settings.market_data_timeout_seconds)
            return await client.get_candles(symbol=symbol, interval=interval, limit=min(limit, 300))

        client = BinanceMarketDataClient(
            base_url=settings.market_data_base_url,
            timeout_seconds=settings.market_data_timeout_seconds,
        )
        return await client.get_candles(symbol=symbol, interval=interval, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MarketDataError:
        try:
            return build_offline_candles(
                symbol=symbol,
                interval=interval,
                limit=min(limit, 300) if selected_exchange == "okx" else limit,
                exchange=selected_exchange,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/symbols", response_model=list[MarketSymbol])
async def get_symbols(
    quote_asset: str | None = Query(default=None, min_length=2, max_length=10),
    exchange: str = Query(default="all", min_length=2, max_length=12),
    current_user: User = Depends(get_current_user)
) -> list[MarketSymbol]:
    settings = get_settings()
    selected_exchange = normalize_exchange(exchange)

    if selected_exchange == "binance":
        return await get_binance_symbols(settings, quote_asset)
    if selected_exchange == "okx":
        return await get_okx_symbols(settings.market_data_timeout_seconds, quote_asset)

    symbols = [
        *await get_binance_symbols(settings, quote_asset),
        *await get_okx_symbols(settings.market_data_timeout_seconds, quote_asset),
    ]
    return sorted(symbols, key=lambda item: (item.exchange, item.symbol))


@router.get("/tickers", response_model=MarketOverview)
async def get_tickers(
    quote_asset: str | None = Query(default="USDT", min_length=2, max_length=10),
    exchange: str = Query(default="all", min_length=2, max_length=12),
    current_user: User = Depends(get_current_user)
) -> MarketOverview:
    settings = get_settings()
    selected_exchange = normalize_exchange(exchange)

    if selected_exchange == "binance":
        return await get_binance_tickers(settings, quote_asset)
    if selected_exchange == "okx":
        return await get_okx_tickers(settings.market_data_timeout_seconds, quote_asset)

    binance = await get_binance_tickers(settings, quote_asset)
    okx = await get_okx_tickers(settings.market_data_timeout_seconds, quote_asset)
    tickers = [*binance.tickers, *okx.tickers]
    tickers.sort(key=lambda item: item.quote_volume, reverse=True)
    normalized_quote = quote_asset.upper().strip() if quote_asset else None
    return MarketOverview(
        source=f"{binance.source}+{okx.source}",
        quote_asset=normalized_quote,
        total=len(tickers),
        tickers=tickers,
    )


async def get_binance_symbols(settings: Settings, quote_asset: str | None) -> list[MarketSymbol]:
    client = BinanceMarketDataClient(
        base_url=settings.market_data_base_url,
        timeout_seconds=settings.market_data_timeout_seconds,
    )
    try:
        return await client.get_symbols(quote_asset=quote_asset)
    except MarketDataError:
        return build_offline_symbols(quote_asset=quote_asset, exchange="binance")


async def get_okx_symbols(timeout_seconds: float, quote_asset: str | None) -> list[MarketSymbol]:
    client = OkxMarketDataClient(timeout_seconds=timeout_seconds)
    try:
        return await client.get_symbols(quote_asset=quote_asset)
    except MarketDataError:
        return build_offline_symbols(quote_asset=quote_asset, exchange="okx")


async def get_binance_tickers(settings: Settings, quote_asset: str | None) -> MarketOverview:
    client = BinanceMarketDataClient(
        base_url=settings.market_data_base_url,
        timeout_seconds=settings.market_data_timeout_seconds,
    )
    try:
        return await client.get_24h_tickers(quote_asset=quote_asset)
    except MarketDataError:
        return build_offline_tickers(quote_asset=quote_asset, exchange="binance")


async def get_okx_tickers(timeout_seconds: float, quote_asset: str | None) -> MarketOverview:
    client = OkxMarketDataClient(timeout_seconds=timeout_seconds)
    try:
        return await client.get_24h_tickers(quote_asset=quote_asset)
    except MarketDataError:
        return build_offline_tickers(quote_asset=quote_asset, exchange="okx")
