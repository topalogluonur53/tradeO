from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)
    logger.info(
        "worker_started_in_safe_idle_mode",
        extra={"trading_mode": settings.trading_mode, "kill_switch_enabled": settings.kill_switch_enabled},
    )


if __name__ == "__main__":
    main()
