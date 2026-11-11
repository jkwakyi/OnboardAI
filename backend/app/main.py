"""OnboardAI backend application factory.

One FastAPI application composed of separated modules (modular monolith);
modules communicate only through interfaces.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.config import get_settings
from app.db import check_connection as check_database
from app.vectorstore import check_connection as check_vectorstore

logger = logging.getLogger(__name__)


def _verify_storage_connections() -> None:
    """Log whether the Main Database and Vector Database are reachable.

    Startup does not abort on failure, so a teammate working on the frontend
    can run the backend before bringing the stores up. The log line names the
    fix.
    """
    try:
        check_database()
        logger.info("Main Database (PostgreSQL) connected.")
    except Exception as exc:  # noqa: BLE001 - reported, not handled
        logger.error("Main Database (PostgreSQL) unreachable: %s. Run: docker compose up -d", exc)

    try:
        check_vectorstore()
        logger.info("Vector Database (ChromaDB) connected.")
    except Exception as exc:  # noqa: BLE001 - reported, not handled
        logger.error("Vector Database (ChromaDB) unreachable: %s. Run: docker compose up -d", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare file storage and report store connectivity on startup."""
    settings = get_settings()
    logging.basicConfig(level=settings.onboardai_log_level)
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    _verify_storage_connections()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="OnboardAI",
        description="AI employee onboarding assistant.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app


app = create_app()
