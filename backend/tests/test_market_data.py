import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.market_data.binance import (
    BinanceMarketDataClient,
    MarketDataError,
    normalize_base_urls,
    parse_exchange_symbol,
    parse_kline,
    parse_ticker,
    validate_market_request,
)
from app.market_data.offline import build_offline_candles, build_offline_symbols, build_offline_tickers
from app.market_data.okx import OkxMarketDataClient, normalize_okx_symbol, parse_okx_symbol, parse_okx_ticker


def test_validate_market_request_normalizes_symbol_and_accepts_supported_interval() -> None:
    symbol, interval, limit = validate_market_request("btc/usdt", "1h", 200)

    assert symbol == "BTCUSDT"
    assert interval == "1h"
    assert limit == 200


@pytest.mark.parametrize(
    ("symbol", "interval", "limit"),
    [
        ("BTC_USDT!", "1h", 200),
        ("BTCUSDT", "13m", 200),
        ("BTCUSDT", "1h", 1001),
    ],
)
def test_validate_market_request_rejects_unsupported_inputs(
    symbol: str,
    interval: str,
    limit: int,
) -> None:
    with pytest.raises(ValueError):
        validate_market_request(symbol, interval, limit)


def test_normalize_base_urls_keeps_configured_url_and_adds_public_fallbacks() -> None:
    urls = normalize_base_urls("https://example.test, https://api.binance.com")

    assert urls[0] == "https://example.test"
    assert urls.count("https://api.binance.com") == 1
    assert "https://data-api.binance.vision" in urls


def test_normalize_okx_symbol_accepts_compact_and_dashed_pairs() -> None:
    assert normalize_okx_symbol("BTCUSDT") == "BTC-USDT"
    assert normalize_okx_symbol("eth-usdc") == "ETH-USDC"


def test_parse_kline_maps_binance_payload_to_candle() -> None:
    candle = parse_kline(
        "BTCUSDT",
        "1h",
        [
            1499040000000,
            "0.01634790",
            "0.80000000",
            "0.01575800",
            "0.01577100",
            "148976.11427815",
            1499644799999,
            "2434.19055334",
            308,
            "1756.87402397",
            "28.46694368",
            "0",
        ],
    )

    assert candle.symbol == "BTCUSDT"
    assert candle.interval == "1h"
    assert candle.open_time == 1499040000000
    assert candle.close == 0.015771
    assert candle.volume == 148976.11427815
    assert candle.trade_count == 308


def test_parse_exchange_symbol_maps_binance_exchange_info_row() -> None:
    symbol = parse_exchange_symbol(
        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        }
    )

    assert symbol.symbol == "BTCUSDT"
    assert symbol.base_asset == "BTC"
    assert symbol.quote_asset == "USDT"
    assert symbol.spot_trading_allowed is True


def test_parse_ticker_maps_binance_24h_row() -> None:
    ticker = parse_ticker(
        {
            "symbol": "BTCUSDT",
            "priceChange": "10.5",
            "priceChangePercent": "1.25",
            "weightedAvgPrice": "101.2",
            "lastPrice": "102.0",
            "lastQty": "0.42",
            "openPrice": "91.5",
            "highPrice": "105.0",
            "lowPrice": "90.0",
            "volume": "1000.0",
            "quoteVolume": "102000.0",
            "count": 1234,
        }
    )

    assert ticker.symbol == "BTCUSDT"
    assert ticker.last_price == 102.0
    assert ticker.price_change_percent == 1.25
    assert ticker.trade_count == 1234


def test_binance_tickers_are_filtered_to_active_spot_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BinanceMarketDataClient("https://example.test", 10)

    async def fake_get_json(path: str, params: object, error_message: str) -> object:
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "status": "TRADING",
                        "isSpotTradingAllowed": True,
                    }
                ]
            }
        if path == "/api/v3/ticker/24hr":
            return [
                {
                    "symbol": "BTCUSDT",
                    "priceChange": "10.5",
                    "priceChangePercent": "1.25",
                    "weightedAvgPrice": "101.2",
                    "lastPrice": "102.0",
                    "lastQty": "0.42",
                    "openPrice": "91.5",
                    "highPrice": "105.0",
                    "lowPrice": "90.0",
                    "volume": "1000.0",
                    "quoteVolume": "102000.0",
                    "count": 1234,
                },
                {
                    "symbol": "XMRUSDT",
                    "priceChange": "5.4",
                    "priceChangePercent": "4.76",
                    "weightedAvgPrice": "114.5",
                    "lastPrice": "118.7",
                    "lastQty": "0.6",
                    "openPrice": "113.3",
                    "highPrice": "119.6",
                    "lowPrice": "110.4",
                    "volume": "5000",
                    "quoteVolume": "574000",
                    "count": 4001,
                },
                {
                    "symbol": "BTCUPUSDT",
                    "priceChange": "0",
                    "priceChangePercent": "0",
                    "weightedAvgPrice": "0",
                    "lastPrice": "0",
                    "lastQty": "0",
                    "openPrice": "0",
                    "highPrice": "0",
                    "lowPrice": "0",
                    "volume": "0",
                    "quoteVolume": "0",
                    "count": 0,
                },
            ]
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    overview = asyncio.run(client.get_24h_tickers("USDT"))

    assert [ticker.symbol for ticker in overview.tickers] == ["BTCUSDT"]


def test_binance_candles_reject_inactive_spot_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BinanceMarketDataClient("https://example.test", 10)

    async def fake_get_json(path: str, params: object, error_message: str) -> object:
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "status": "TRADING",
                        "isSpotTradingAllowed": True,
                    }
                ]
            }
        raise AssertionError("Inactive symbols must be rejected before klines are requested")

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    with pytest.raises(ValueError, match="not an active Binance spot symbol"):
        asyncio.run(client.get_candles("XMRUSDT", "1h", 5))


def test_parse_okx_payloads_map_to_market_models() -> None:
    symbol = parse_okx_symbol(
        {
            "instId": "BTC-USDT",
            "baseCcy": "BTC",
            "quoteCcy": "USDT",
            "state": "live",
        }
    )
    ticker = parse_okx_ticker(
        {
            "instId": "BTC-USDT",
            "last": "105.0",
            "lastSz": "0.5",
            "open24h": "100.0",
            "high24h": "110.0",
            "low24h": "95.0",
            "vol24h": "1000",
            "volCcy24h": "105000",
        }
    )

    assert symbol.exchange == "okx"
    assert symbol.symbol == "BTC-USDT"
    assert ticker.exchange == "okx"
    assert ticker.price_change == 5.0
    assert ticker.price_change_percent == 5.0


def test_offline_market_data_is_deterministic_and_valid() -> None:
    series = build_offline_candles("BTCUSDT", "1h", 60)
    symbols = build_offline_symbols("USDT")
    overview = build_offline_tickers("USDT")

    okx_symbols = build_offline_symbols("USDT", exchange="okx")
    okx_series = build_offline_candles("BTC-USDT", "1h", 60, exchange="okx")
    later_series = build_offline_candles("BTC-USDT", "1h", 60, exchange="okx", cursor=4)

    assert series.source == "offline_paper_binance_market_data_usdt"
    assert okx_series.symbol == "BTC-USDT"
    assert okx_series.candles[0].symbol == "BTC-USDT"
    assert later_series.candles[-1].open_time > okx_series.candles[-1].open_time
    assert later_series.candles[-1].close != okx_series.candles[-1].close
    assert len(series.candles) == 60
    assert series.candles[0].open_time < series.candles[-1].open_time
    assert all(candle.low <= candle.close <= candle.high for candle in series.candles)
    assert any(symbol.symbol == "BTCUSDT" for symbol in symbols)
    assert any(symbol.symbol == "BTC-USDT" for symbol in okx_symbols)
    assert overview.source == "offline_paper_binance_24h_ticker"
    assert overview.total == len(overview.tickers)
    assert overview.total > 50


def test_offline_market_data_excludes_known_inactive_spot_pairs() -> None:
    assert all(symbol.symbol != "XMRUSDT" for symbol in build_offline_symbols("USDT", exchange="binance"))
    assert all(symbol.symbol != "XMR-USDT" for symbol in build_offline_symbols("USDT", exchange="okx"))

    with pytest.raises(ValueError, match="not an active paper spot symbol"):
        build_offline_candles("XMRUSDT", "1h", 60, exchange="binance")


def test_market_routes_fall_back_to_offline_data(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable(*args: object, **kwargs: object) -> object:
        raise MarketDataError("offline in test")

    monkeypatch.setattr(BinanceMarketDataClient, "get_candles", unavailable)
    monkeypatch.setattr(BinanceMarketDataClient, "get_symbols", unavailable)
    monkeypatch.setattr(BinanceMarketDataClient, "get_24h_tickers", unavailable)
    monkeypatch.setattr(OkxMarketDataClient, "get_candles", unavailable)
    monkeypatch.setattr(OkxMarketDataClient, "get_symbols", unavailable)
    monkeypatch.setattr(OkxMarketDataClient, "get_24h_tickers", unavailable)

    with TestClient(app) as client:
        candles = client.get("/api/market-data/candles?symbol=BTCUSDT&interval=1h&limit=60")
        okx_candles = client.get("/api/market-data/candles?symbol=BTC-USDT&interval=1h&limit=60&exchange=okx")
        symbols = client.get("/api/market-data/symbols?quote_asset=USDT")
        tickers = client.get("/api/market-data/tickers?quote_asset=USDT")

    assert candles.status_code == 200
    assert candles.json()["source"] == "offline_paper_binance_market_data_usdt"
    assert okx_candles.status_code == 200
    assert okx_candles.json()["source"] == "offline_paper_okx_market_data_usdt"
    assert symbols.status_code == 200
    assert any(symbol["symbol"] == "BTCUSDT" for symbol in symbols.json())
    assert any(symbol["symbol"] == "BTC-USDT" for symbol in symbols.json())
    assert len(symbols.json()) > 100
    assert tickers.status_code == 200
    assert tickers.json()["total"] > 100
