import asyncio
import logging
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.trading import AutomationState
from app.models.user import User
from app.trading.multi_tenant import execute_trading_step_for_user
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

async def run_trading_worker():
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info("Trading Worker initialized and starting...")
    
    while True:
        try:
            db: Session = SessionLocal()
            try:
                # Find all active automation states
                active_states = db.query(AutomationState).filter(AutomationState.enabled == True).all()
                
                # Execute step for each user
                for state in active_states:
                    user = db.query(User).filter(User.id == state.user_id).first()
                    if user and not user.trading_halted:
                        try:
                            await execute_trading_step_for_user(
                                db=db,
                                user=user,
                                symbol=state.symbol,
                                interval=state.interval,
                                exchange=state.exchange
                            )
                        except Exception as e:
                            logger.error(f"Error executing step for user {user.id}: {e}", exc_info=True)
                            
                            # Mark error in automation state
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
