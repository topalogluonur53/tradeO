import asyncio
import logging
import os
from sqlalchemy.orm import Session
from app.db.session import get_session_factory
from app.models.trading import AutomationState
from app.models.user import User
from app.trading.multi_tenant import execute_trading_step_for_user
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.market_data.binance import BinanceMarketDataClient
from app.trading.strategy_engine import NexusAIStrategy

async def get_best_symbol_to_trade(symbols_to_scan, interval, user):
    settings = get_settings()
    client = BinanceMarketDataClient(base_url=settings.market_data_base_url, timeout_seconds=settings.market_data_timeout_seconds)
    strategy = NexusAIStrategy(
        bollinger_width=user.strategy_bollinger_width,
        rsi_min=user.strategy_rsi_min,
        rsi_max=user.strategy_rsi_max,
        volume_multiplier=user.strategy_volume_multiplier,
        macd_enabled=user.strategy_macd_enabled,
        stoch_enabled=user.strategy_stoch_enabled,
    )
    
    best_symbol = None
    best_confidence = -1.0
    
    for sym in symbols_to_scan:
        try:
            # Multi-Timeframe Check (MTF)
            if user.mtf_enabled:
                # Higher timeframe check (e.g. 4h trend)
                htf_series = await client.get_candles(symbol=sym, interval="4h", limit=50)
                if len(htf_series.candles) >= 30:
                    from app.trading.indicators import calculate_indicator_snapshot
                    htf_inds = calculate_indicator_snapshot(htf_series.candles)
                    if htf_inds["ema_fast"] <= htf_inds["ema_slow"]:
                        await asyncio.sleep(0.5)
                        continue # 4H trend is down, skip this coin

            series = await client.get_candles(symbol=sym, interval=interval, limit=120)
            signal = strategy.generate_signal(sym, series.candles)
            if signal.side.value == "BUY" and signal.confidence > best_confidence:
                best_confidence = signal.confidence
                best_symbol = sym
        except Exception:
            pass
        await asyncio.sleep(0.5) # Borsa rate limit korumasi
        
    return best_symbol

async def run_trading_worker():
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info("Trading Worker initialized and starting...")
    
    # Kullanici tarafindan .env'de WATCHLIST_SYMBOLS belirtilmis mi kontrol et
    env_watchlist = os.getenv("WATCHLIST_SYMBOLS", "").strip()
    if env_watchlist:
        default_symbols = [s.strip().upper() for s in env_watchlist.split(",") if s.strip()]
        logger.info(f"Ozel izleme listesi (Watchlist) kullaniliyor: {default_symbols}")
    else:
        default_symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
            "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT"
        ]
        logger.info(f"Varsayilan izleme listesi kullaniliyor: {default_symbols}")
    
    while True:
        try:
            db: Session = get_session_factory()()
            try:
                # Find all active automation states
                active_states = db.query(AutomationState).filter(AutomationState.enabled == True).all()
                
                # Execute step for each user
                for state in active_states:
                    user = db.query(User).filter(User.id == state.user_id).first()
                    if user and not user.trading_halted:
                        try:
                            # 1. Taranacak coinleri ve en iyi firsati bul
                            target_symbol = await get_best_symbol_to_trade(default_symbols, state.interval, user)
                            
                            # 2. Eger alim sinyali veren hicbir coin yoksa, ilk coini (veya defaultu) secip hold durumunu kaydet
                            if not target_symbol:
                                target_symbol = state.symbol if state.symbol in default_symbols else default_symbols[0]
                                
                            # 3. Bulunan en iyi coin icin veya hold icin botu calistir
                            await execute_trading_step_for_user(
                                db=db,
                                user=user,
                                symbol=target_symbol,
                                interval=state.interval,
                                exchange=state.exchange
                            )
                        except Exception as e:
                            logger.error(f"Error executing step for user {user.id}: {e}", exc_info=True)
                            state.last_action = "AUTO_ERROR"
                            state.last_reason = str(e)
                            db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger = get_logger(__name__)
            logger.error(f"Trading Worker encountered a critical error: {e}", exc_info=True)
            
        # Sleep for the configured interval
        await asyncio.sleep(settings.paper_trade_interval_seconds)

def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(run_trading_worker())

if __name__ == "__main__":
    main()
