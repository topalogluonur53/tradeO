from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User

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
    strategy_bollinger_width: float = 0.08
    strategy_rsi_min: float = 35.0
    strategy_rsi_max: float = 70.0
    strategy_volume_multiplier: float = 0.6


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
    user: User,
) -> SystemStatusResponse:
    return SystemStatusResponse(
        trading_mode=user.trading_mode,
        trading_halted=user.trading_halted,
        halt_reason=user.halt_reason or "PAPER_MODE_READY",
        worker_state="halted" if user.trading_halted else "safe_idle",
        updated_at=datetime.now(timezone.utc),
        risk_limits=RiskLimitsResponse(
            risk_per_trade=user.risk_per_trade,
            max_single_position_pct=user.max_single_position_pct,
            max_total_exposure_pct=user.max_total_exposure_pct,
            max_open_positions=user.max_open_positions,
            daily_loss_limit_pct=user.daily_loss_limit_pct,
            max_drawdown_limit_pct=user.max_drawdown_limit_pct,
            min_risk_reward=user.min_risk_reward,
            cooldown_after_losses=user.cooldown_after_losses,
            strategy_bollinger_width=user.strategy_bollinger_width,
            strategy_rsi_min=user.strategy_rsi_min,
            strategy_rsi_max=user.strategy_rsi_max,
            strategy_volume_multiplier=user.strategy_volume_multiplier,
        ),
    )


@router.get("/status", response_model=SystemStatusResponse)
def system_status(current_user: User = Depends(get_current_user)) -> SystemStatusResponse:
    return build_status(current_user)


@router.post("/emergency-stop", response_model=SystemStatusResponse)
def emergency_stop(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> SystemStatusResponse:
    current_user.trading_halted = True
    current_user.halt_reason = "MANUAL_EMERGENCY_STOP"
    db.commit()
    logger.warning("paper_trading_emergency_stop_enabled", extra={"user_id": current_user.id})
    return build_status(current_user)


@router.post("/resume", response_model=SystemStatusResponse)
def resume_paper_mode(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> SystemStatusResponse:
    current_user.trading_halted = False
    current_user.halt_reason = "PAPER_MODE_READY"
    db.commit()
    logger.info("paper_trading_resumed", extra={"user_id": current_user.id})
    return build_status(current_user)


class UpdateRiskLimitsRequest(BaseModel):
    risk_per_trade: float | None = Field(default=None, gt=0.0, le=0.05)
    max_single_position_pct: float | None = Field(default=None, gt=0.0, le=1.0)
    max_total_exposure_pct: float | None = Field(default=None, gt=0.0, le=1.0)
    max_open_positions: int | None = Field(default=None, ge=1, le=50)
    daily_loss_limit_pct: float | None = Field(default=None, gt=0.0, le=0.5)
    max_drawdown_limit_pct: float | None = Field(default=None, gt=0.0, le=0.8)
    min_risk_reward: float | None = Field(default=None, ge=1.0, le=10.0)
    cooldown_after_losses: int | None = Field(default=None, ge=0, le=20)
    strategy_bollinger_width: float | None = Field(default=None, ge=0.01, le=0.5)
    strategy_rsi_min: float | None = Field(default=None, ge=0.0, le=100.0)
    strategy_rsi_max: float | None = Field(default=None, ge=0.0, le=100.0)
    strategy_volume_multiplier: float | None = Field(default=None, ge=0.0, le=5.0)


@router.put("/risk-limits", response_model=SystemStatusResponse)
def update_risk_limits(
    req: UpdateRiskLimitsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> SystemStatusResponse:
    updates = req.model_dump(exclude_unset=True)
    next_single_position_pct = updates.get(
        "max_single_position_pct", current_user.max_single_position_pct
    )
    next_total_exposure_pct = updates.get(
        "max_total_exposure_pct", current_user.max_total_exposure_pct
    )
    if next_total_exposure_pct < next_single_position_pct:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="max_total_exposure_pct must be greater than or equal to max_single_position_pct",
        )

    for key, value in updates.items():
        setattr(current_user, key, value)

    db.commit()
    logger.info("risk_limits_updated", extra={"user_id": current_user.id, "updates": updates})
    return build_status(current_user)
