import asyncio
import logging
from sqlalchemy.orm import Session
from app.db.session import get_session_factory
from app.models.trading import AutomationState
from app.models.user import User
from app.trading.multi_tenant import execute_trading_step_for_user
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

async def run_trading_worker():
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info("Trading Worker initialized")
    session_factory = get_session_factory()
    semaphore = asyncio.Semaphore(settings.worker_max_concurrency)

    async def process_state(state_id: int) -> None:
        async with semaphore:
            db: Session = session_factory()
            try:
                state = db.get(AutomationState, state_id)
                if state is None or not state.enabled or not state.running:
                    return
                user = db.get(User, state.user_id)
                if user is None or user.trading_halted:
                    return

                result = await execute_trading_step_for_user(
                    db=db,
                    user=user,
                    symbol=state.symbol,
                    interval=state.interval,
                    exchange=state.exchange,
                    automation_only=True,
                )
                logger.info(
                    "paper_scan_cycle",
                    extra={
                        "user_id": user.id,
                        "action": result.action,
                        "symbol": result.signal.symbol if result.signal else state.symbol,
                        "reason": result.reason,
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                db.rollback()
                state = db.get(AutomationState, state_id)
                logger.error("Error executing paper cycle %s: %s", state_id, exc, exc_info=True)
                if state is not None:
                    state.last_action = "AUTO_ERROR"
                    state.last_reason = str(exc)[:255]
                    try:
                        db.commit()
                    except Exception as commit_exc:
                        db.rollback()
                        logger.error("Failed to commit AUTO_ERROR state for %s: %s", state_id, commit_exc)
            finally:
                db.close()

    while True:
        cycle_started = asyncio.get_running_loop().time()
        try:
            db: Session = session_factory()
            try:
                active_state_ids = [
                    state.id
                    for state in db.query(AutomationState)
                    .filter(AutomationState.enabled.is_(True), AutomationState.running.is_(True))
                    .all()
                ]
            finally:
                db.close()
            if active_state_ids:
                await asyncio.gather(*(process_state(state_id) for state_id in active_state_ids))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Trading Worker encountered a critical error: %s", exc, exc_info=True)

        elapsed = asyncio.get_running_loop().time() - cycle_started
        await asyncio.sleep(max(1.0, settings.paper_trade_interval_seconds - elapsed))

def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(run_trading_worker())

if __name__ == "__main__":
    main()
