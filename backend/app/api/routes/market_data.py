from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import get_settings
from app.market_data.binance import BinanceMarketDataClient, MarketDataError
from app.market_data.schemas import CandleSeries, MarketOverview, MarketSymbol

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/candles", response_model=CandleSeries)
async def get_candles(
    symbol: str = Query(default="BTCUSDT", min_length=3, max_length=20),
    interval: str = Query(default="1h", min_length=2, max_length=3),
    limit: int = Query(default=200, ge=1, le=1000),
) -> CandleSeries:
    settings = get_settings()
    client = BinanceMarketDataClient(
        base_url=settings.market_data_base_url,
        timeout_seconds=settings.market_data_timeout_seconds,
    )

    try:
        return await client.get_candles(symbol=symbol, interval=interval, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/symbols", response_model=list[MarketSymbol])
async def get_symbols(
    quote_asset: str | None = Query(default=None, min_length=2, max_length=10),
) -> list[MarketSymbol]:
    settings = get_settings()
    client = BinanceMarketDataClient(
        base_url=settings.market_data_base_url,
        timeout_seconds=settings.market_data_timeout_seconds,
    )

    try:
        return await client.get_symbols(quote_asset=quote_asset)
    except MarketDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/tickers", response_model=MarketOverview)
async def get_tickers(
    quote_asset: str | None = Query(default="USDT", min_length=2, max_length=10),
) -> MarketOverview:
    settings = get_settings()
    client = BinanceMarketDataClient(
        base_url=settings.market_data_base_url,
        timeout_seconds=settings.market_data_timeout_seconds,
    )

    try:
        return await client.get_24h_tickers(quote_asset=quote_asset)
    except MarketDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
