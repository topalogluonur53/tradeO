import asyncio
from app.market_data.binance import BinanceMarketDataClient
from app.trading.strategy_engine import NexusAIStrategy
from app.core.config import get_settings

async def main():
    s = get_settings()
    c = BinanceMarketDataClient(base_url=s.market_data_base_url, timeout_seconds=s.market_data_timeout_seconds)
    strategy = NexusAIStrategy(bollinger_width=0.08, rsi_min=35.0, rsi_max=70.0, volume_multiplier=0.6)
    
    coins = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','ADAUSDT','AVAXUSDT','DOGEUSDT','DOTUSDT','LINKUSDT']
    
    print("=== MEVCUT PARAMETRELER (bollinger<8%, rsi 35-70, vol>=0.6) ===\n")
    for sym in coins:
        series = await c.get_candles(sym, '1h', 120)
        sig = strategy.generate_signal(sym, series.candles)
        inds = sig.indicators
        failed = [f.key for f in sig.filters if not f.passed]
        print(f"{sym:12s} bb={inds['bb_bandwidth']*100:6.2f}%  rsi={inds['rsi']:5.1f}  vol={inds['volume_score']:.2f}  => {sig.side.value:4s}  failed={failed}")
    
    # Test with relaxed params
    strategy2 = NexusAIStrategy(bollinger_width=0.15, rsi_min=25.0, rsi_max=78.0, volume_multiplier=0.3)
    print("\n=== GEVSETiLMiS PARAMETRELER (bollinger<15%, rsi 25-78, vol>=0.3) ===\n")
    for sym in coins:
        series = await c.get_candles(sym, '1h', 120)
        sig = strategy2.generate_signal(sym, series.candles)
        inds = sig.indicators
        failed = [f.key for f in sig.filters if not f.passed]
        print(f"{sym:12s} bb={inds['bb_bandwidth']*100:6.2f}%  rsi={inds['rsi']:5.1f}  vol={inds['volume_score']:.2f}  => {sig.side.value:4s}  failed={failed}")

asyncio.run(main())
