from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.trading.control import TradingControlSnapshot, trading_control

router = APIRouter(prefix="/system", tags=["system"])
logger = get_logger(__name__)


class RiskLimitsResponse(BaseModel):
    risk_per_trade: float
    max_single_position_pct: float
    max_total_exposure_pct: float
    max_open_positions: int
    daily_loss_limit_pct: float
    max_drawdown_limit_pct: float
    min_risk_reward: float
    cooldown_after_losses: int
    stop_loss_required: bool = True


class SystemStatusResponse(BaseModel):
    trading_mode: Literal["paper", "testnet"]
    trading_halted: bool
    halt_reason: str
    worker_state: Literal["safe_idle", "halted"]
    live_orders_enabled: bool = False
    ai_order_access: bool = False
    exchange_keys_configured: bool = False
    updated_at: datetime
    risk_limits: RiskLimitsResponse


def build_status(
    settings: Settings,
    snapshot: TradingControlSnapshot,
) -> SystemStatusResponse:
    return SystemStatusResponse(
        trading_mode=settings.trading_mode,
        trading_halted=snapshot.halted,
        halt_reason=snapshot.reason,
        worker_state="halted" if snapshot.halted else "safe_idle",
        updated_at=snapshot.updated_at,
        risk_limits=RiskLimitsResponse(
            risk_per_trade=settings.risk_per_trade,
            max_single_position_pct=settings.max_single_position_pct,
            max_total_exposure_pct=settings.max_total_exposure_pct,
            max_open_positions=settings.max_open_positions,
            daily_loss_limit_pct=settings.daily_loss_limit_pct,
            max_drawdown_limit_pct=settings.max_drawdown_limit_pct,
            min_risk_reward=settings.min_risk_reward,
            cooldown_after_losses=settings.cooldown_after_losses,
        ),
    )


@router.get("/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    return build_status(get_settings(), trading_control.snapshot())


@router.post("/emergency-stop", response_model=SystemStatusResponse)
def emergency_stop() -> SystemStatusResponse:
    snapshot = trading_control.emergency_stop()
    logger.warning("paper_trading_emergency_stop_enabled")
    return build_status(get_settings(), snapshot)


@router.post("/resume", response_model=SystemStatusResponse)
def resume_paper_mode() -> SystemStatusResponse:
    snapshot = trading_control.resume_paper_mode()
    logger.info("paper_trading_resumed")
    return build_status(get_settings(), snapshot)


class UpdateRiskLimitsRequest(BaseModel):
    risk_per_trade: float | None = None
    max_single_position_pct: float | None = None
    max_total_exposure_pct: float | None = None
    max_open_positions: int | None = None
    daily_loss_limit_pct: float | None = None
    max_drawdown_limit_pct: float | None = None
    min_risk_reward: float | None = None
    cooldown_after_losses: int | None = None


@router.put("/risk-limits", response_model=SystemStatusResponse)
def update_risk_limits(req: UpdateRiskLimitsRequest) -> SystemStatusResponse:
    settings = get_settings()
    updates = req.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    logger.info("risk_limits_updated", extra={"updates": updates})
    return build_status(settings, trading_control.snapshot())


