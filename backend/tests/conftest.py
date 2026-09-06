"""Shared isolated database and authenticated user for API tests."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi import Depends
from sqlalchemy.orm import Session


_temp_db = tempfile.NamedTemporaryFile(prefix="tradeo-pytest-", suffix=".db", delete=False)
_temp_db.close()
_test_db_path = Path(_temp_db.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path.as_posix()}"

from app.api.routes.auth import get_current_user  # noqa: E402
from app.db.session import get_db, get_engine, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.trading import AutomationState, PaperPortfolio, PaperPosition, PaperTrade  # noqa: E402
from app.models.user import User  # noqa: E402
from app.trading.control import trading_control  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database() -> None:
    Base.metadata.create_all(bind=get_engine())
    yield
    get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    _test_db_path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def authenticated_api_user() -> None:
    factory = get_session_factory()
    session = factory()
    try:
        session.query(PaperTrade).delete()
        session.query(PaperPosition).delete()
        session.query(PaperPortfolio).delete()
        session.query(AutomationState).delete()
        session.query(User).delete()
        session.add(
            User(
                id=1,
                username="test-user",
                hashed_password="not-used-by-api-tests",
                is_active=True,
                is_admin=True,
                risk_per_trade=0.005,
                max_single_position_pct=0.50,
                max_total_exposure_pct=1.00,
                max_open_positions=3,
                daily_loss_limit_pct=0.02,
                max_drawdown_limit_pct=0.08,
                min_risk_reward=1.5,
                cooldown_after_losses=3,
                strategy_bollinger_width=0.15,
                strategy_rsi_min=25.0,
                strategy_rsi_max=78.0,
                strategy_volume_multiplier=0.3,
                strategy_macd_enabled=False,
                strategy_stoch_enabled=False,
                mtf_enabled=False,
                trailing_stop_enabled=False,
                trailing_stop_distance_pct=0.03,
                is_automation_enabled=False,
                trading_mode="paper",
                trading_halted=False,
                halt_reason="PAPER_MODE_READY",
            )
        )
        session.commit()
    finally:
        session.close()

    def current_test_user(db: Session = Depends(get_db)) -> User:
        user = db.get(User, 1)
        assert user is not None
        return user

    app.dependency_overrides[get_current_user] = current_test_user
    trading_control.resume_paper_mode()
    yield
    app.dependency_overrides.pop(get_current_user, None)
    trading_control.resume_paper_mode()
