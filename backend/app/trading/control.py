from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock

from app.core.config import get_settings


@dataclass(frozen=True)
class TradingControlSnapshot:
    halted: bool
    reason: str
    updated_at: datetime


class TradingControl:
    def __init__(self, initially_halted: bool = False) -> None:
        self._lock = RLock()
        self._halted = initially_halted
        self._reason = "CONFIGURED_KILL_SWITCH" if initially_halted else "PAPER_MODE_READY"
        self._updated_at = datetime.now(UTC)

    def snapshot(self) -> TradingControlSnapshot:
        with self._lock:
            return TradingControlSnapshot(
                halted=self._halted,
                reason=self._reason,
                updated_at=self._updated_at,
            )

    def emergency_stop(self) -> TradingControlSnapshot:
        with self._lock:
            self._halted = True
            self._reason = "MANUAL_EMERGENCY_STOP"
            self._updated_at = datetime.now(UTC)
            return self.snapshot()

    def resume_paper_mode(self) -> TradingControlSnapshot:
        with self._lock:
            self._halted = False
            self._reason = "PAPER_MODE_READY"
            self._updated_at = datetime.now(UTC)
            return self.snapshot()


trading_control = TradingControl(initially_halted=get_settings().kill_switch_enabled)
