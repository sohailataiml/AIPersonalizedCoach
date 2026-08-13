"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import build_services, get_services, set_services
from app.api.routes import router
from app.core.config import get_settings
from app.mcp import mcp_asgi_app, mcp_session_lifespan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    services = build_services(settings)
    set_services(services)
    logger.info(
        "startup graph_backend=%s llm_provider=%s",
        services.backend,
        getattr(services.llm, "name", "unknown"),
    )
    try:
        # Starlette's Mount does not run a sub-app's lifespan, so the MCP session
        # manager has to be started here or /mcp fails at request time.
        async with mcp_session_lifespan():
            yield
    finally:
        services.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Future Coach Intelligence Platform",
        description=(
            "Knowledge-graph backed coach dashboard. Exercise safety is decided by "
            "deterministic graph traversal, not by the language model."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    # The AI-facing interface, mounted alongside - never in place of - the REST
    # API. Both reach the same Services container, so a safety decision cannot
    # differ depending on which interface asked. Mounted rather than run as a
    # sibling process precisely to keep that container shared.
    app.mount("/mcp", mcp_asgi_app(path="/"))

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "future-coach-intelligence-platform",
            "docs": "/docs",
            "health": "/api/health",
            "mcp": "/mcp",
        }

    return app


app = create_app()

__all__ = ["app", "create_app", "get_services"]
