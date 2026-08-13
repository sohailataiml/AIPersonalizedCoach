"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import build_services, get_services, set_services
from app.api.routes import router
from app.api.schemas import LivenessResponse, ReadinessResponse
from app.core.config import get_settings
from app.graph.bootstrap import GraphBackendUnavailableError
from app.mcp import mcp_asgi_app, mcp_session_lifespan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the service container, then hand off.

    A graph that cannot be reached does **not** crash the process: the app
    still starts so ``/health/live`` answers and the failure is diagnosable
    from the outside. What it does not do is quietly continue on a different
    storage engine - readiness stays false and says why.
    """
    settings = get_settings()
    app.state.startup_error = None
    services = None

    try:
        services = build_services(settings)
        set_services(services)
        logger.info(
            "startup env=%s graph_backend=%s llm_provider=%s seeded=%s",
            settings.environment,
            services.backend,
            getattr(services.llm, "name", "unknown"),
            services.bootstrap.seeded if services.bootstrap else "n/a",
        )
    except GraphBackendUnavailableError as exc:
        # The message is already credential-free (scheme/host/port only).
        app.state.startup_error = str(exc)
        logger.error("startup failed: %s", exc)

    try:
        # Starlette's Mount does not run a sub-app's lifespan, so the MCP session
        # manager has to be started here or /mcp fails at request time.
        async with mcp_session_lifespan():
            yield
    finally:
        if services is not None:
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
    # Narrow by construction: local development origins plus the deployed
    # frontend when one is configured. Never ["*"] - the API allows
    # credentials, and a wildcard with credentials is both invalid and an
    # invitation.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
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
            "health": "/health/ready",
            "mcp": "/mcp",
        }

    # --- health -----------------------------------------------------------
    #
    # Two distinct questions, deliberately not merged:
    #
    #   /health/live   is this process running?
    #   /health/ready  can it actually serve? (graph reachable AND seeded)
    #
    # A platform that restarts on a failing liveness probe must not restart a
    # healthy process because a database is slow - hence the split. Neither
    # response carries a credential, a URI or a stack trace.

    @app.get("/health/live", response_model=LivenessResponse, tags=["health"])
    def health_live() -> LivenessResponse:
        return LivenessResponse(status="alive", version=app.version)

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    def health_ready(response: Response) -> ReadinessResponse:
        settings = get_settings()
        startup_error = getattr(app.state, "startup_error", None)

        try:
            services = get_services()
        except RuntimeError:
            services = None

        bootstrap = services.bootstrap if services else None
        reachable = bool(bootstrap and bootstrap.reachable)
        seeded = bool(bootstrap and bootstrap.seeded)
        ready = services is not None and reachable and seeded and not startup_error

        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return ReadinessResponse(
            status="ready" if ready else "not_ready",
            environment=settings.environment,
            graph_backend=services.backend if services else settings.graph_backend,
            graph_reachable=reachable,
            graph_seeded=seeded,
            seed_version=bootstrap.seed_version if bootstrap else None,
            mcp_enabled=settings.mcp_enabled,
            # Verification problems are safe to surface: they name counts, not
            # connection details. The startup error is already redacted to
            # scheme/host/port by `safe_target`.
            problems=list(bootstrap.problems) if bootstrap else (
                [startup_error] if startup_error else ["services not initialized"]
            ),
        )

    return app


app = create_app()

__all__ = ["app", "create_app", "get_services"]
