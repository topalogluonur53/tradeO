from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.system import router as system_router
from app.api.routes.trading import router as trading_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)

    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(market_data_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(trading_router, prefix="/api")

    logger.info("application_configured", extra={"environment": settings.environment})
    return app


app = create_app()
