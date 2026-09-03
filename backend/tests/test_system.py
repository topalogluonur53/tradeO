from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.trading.control import trading_control


def test_system_status_exposes_safe_paper_mode_limits() -> None:
    trading_control.resume_paper_mode()

    with TestClient(app) as client:
        response = client.get("/api/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trading_mode"] == "paper"
    assert payload["trading_halted"] is False
    assert payload["live_orders_enabled"] is False
    assert payload["ai_order_access"] is False
    assert payload["risk_limits"]["risk_per_trade"] == 0.005
    assert payload["risk_limits"]["stop_loss_required"] is True


def test_emergency_stop_and_resume_update_shared_control_state() -> None:
    trading_control.resume_paper_mode()

    with TestClient(app) as client:
        stopped = client.post("/api/system/emergency-stop")
        status = client.get("/api/system/status")
        resumed = client.post("/api/system/resume")

    assert stopped.status_code == 200
    assert stopped.json()["trading_halted"] is True
    assert status.json()["halt_reason"] == "MANUAL_EMERGENCY_STOP"
    assert resumed.status_code == 200
    assert resumed.json()["trading_halted"] is False


def test_update_risk_limits_applies_safe_values() -> None:
    settings = get_settings()
    original = {
        "risk_per_trade": settings.risk_per_trade,
        "max_single_position_pct": settings.max_single_position_pct,
        "max_total_exposure_pct": settings.max_total_exposure_pct,
        "max_open_positions": settings.max_open_positions,
        "daily_loss_limit_pct": settings.daily_loss_limit_pct,
        "max_drawdown_limit_pct": settings.max_drawdown_limit_pct,
        "min_risk_reward": settings.min_risk_reward,
        "cooldown_after_losses": settings.cooldown_after_losses,
    }

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/system/risk-limits",
                json={
                    "risk_per_trade": 0.01,
                    "max_single_position_pct": 0.15,
                    "max_total_exposure_pct": 0.35,
                    "max_open_positions": 4,
                    "daily_loss_limit_pct": 0.03,
                    "max_drawdown_limit_pct": 0.12,
                    "min_risk_reward": 2.0,
                    "cooldown_after_losses": 4,
                },
            )

        assert response.status_code == 200
        limits = response.json()["risk_limits"]
        assert limits["risk_per_trade"] == 0.01
        assert limits["max_single_position_pct"] == 0.15
        assert limits["max_total_exposure_pct"] == 0.35
        assert limits["max_open_positions"] == 4
        assert limits["daily_loss_limit_pct"] == 0.03
        assert limits["max_drawdown_limit_pct"] == 0.12
        assert limits["min_risk_reward"] == 2.0
        assert limits["cooldown_after_losses"] == 4
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def test_update_risk_limits_rejects_unsafe_values() -> None:
    with TestClient(app) as client:
        negative_risk = client.put("/api/system/risk-limits", json={"risk_per_trade": -0.01})
        impossible_exposure = client.put(
            "/api/system/risk-limits",
            json={"max_single_position_pct": 0.4, "max_total_exposure_pct": 0.2},
        )

    assert negative_risk.status_code == 422
    assert impossible_exposure.status_code == 422
