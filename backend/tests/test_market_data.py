import pytest

from app.market_data.binance import parse_exchange_symbol, parse_kline, parse_ticker, validate_market_request


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
