from pydantic import BaseModel, Field


class Candle(BaseModel):
    symbol: str
    interval: str
    open_time: int = Field(description="Unix timestamp in milliseconds")
    close_time: int = Field(description="Unix timestamp in milliseconds")
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int


class CandleSeries(BaseModel):
    symbol: str
    interval: str
    source: str
    exchange: str = "binance"
    candles: list[Candle]


class MarketSymbol(BaseModel):
    exchange: str = "binance"
    symbol: str
    base_asset: str
    quote_asset: str
    status: str
    spot_trading_allowed: bool


class MarketTicker(BaseModel):
    exchange: str = "binance"
    symbol: str
    price_change: float
    price_change_percent: float
    weighted_average_price: float
    last_price: float
    last_quantity: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float
    trade_count: int


class MarketOverview(BaseModel):
    source: str
    quote_asset: str | None
    total: int
    tickers: list[MarketTicker]
