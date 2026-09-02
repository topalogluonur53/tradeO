from dataclasses import dataclass

from app.trading.schemas import Signal
from app.trading.control import trading_control


@dataclass(frozen=True)
class OrderValidationContext:
    kill_switch_enabled: bool
    latest_price: float
    max_price_age_seconds: int
    price_age_seconds: int
    duplicate_client_order_id: bool = False


class OrderValidator:
    def validate(self, signal: Signal, context: OrderValidationContext) -> tuple[bool, str]:
        if context.kill_switch_enabled or trading_control.snapshot().halted:
            return False, "KILL_SWITCH_ENABLED"
        if signal.stop_loss <= 0:
            return False, "STOP_LOSS_REQUIRED"
        if context.duplicate_client_order_id:
            return False, "DUPLICATE_ORDER_REJECTED"
        if context.price_age_seconds > context.max_price_age_seconds:
            return False, "STALE_PRICE_REJECTED"
        if context.latest_price <= 0:
            return False, "INVALID_MARKET_PRICE"
        return True, "VALID_FOR_PAPER_EXECUTION"
