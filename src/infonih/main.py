from fastapi import FastAPI
from loguru import logger

from infonih.api.routes import health
from infonih.config import settings


def create_app() -> FastAPI:
    logger.info("starting {app}", app=settings.app_name)
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.include_router(health.router)
    return app


app = create_app()
