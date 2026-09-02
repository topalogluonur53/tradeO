from fastapi.testclient import TestClient

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
