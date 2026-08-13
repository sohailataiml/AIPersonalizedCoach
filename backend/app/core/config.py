"""Application configuration.

Every knob is environment-driven so a reviewer can run the stack with zero
secrets (in-memory graph + stub LLM) or with the full Neo4j + provider setup.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- data -----------------------------------------------------------
    exercises_path: Path = REPO_ROOT / "data" / "exercises.json"
    member_context_path: Path = REPO_ROOT / "data" / "member-context.json"

    # --- graph ----------------------------------------------------------
    # "memory" keeps the whole app runnable without Docker; "neo4j" is the
    # documented default for the full experience. Both implement the same
    # GraphRepository protocol, so safety logic is identical either way.
    graph_backend: Literal["memory", "neo4j"] = "memory"
    neo4j_uri: str = "bolt://localhost:7687"
    #: Set by the deployment from Render's private-service reference
    #: (`fromService … property: host`). Preferred over ``neo4j_uri`` when
    #: present, so the hostname is resolved by the platform rather than guessed
    #: in a config file. Blueprints cannot concatenate values, hence host+port
    #: rather than a ready-made URI.
    neo4j_host: str | None = None
    neo4j_port: int = 7687
    neo4j_user: str = "neo4j"
    neo4j_password: str = "futurecoach"
    neo4j_database: str = "neo4j"

    # FastAPI can start before Neo4j finishes booting, so the first connection
    # attempt is expected to fail on a cold deploy. Bounded on purpose: an
    # unbounded retry turns a misconfiguration into a service that never starts
    # and never explains why.
    neo4j_connect_attempts: int = 12
    #: Per-attempt driver timeout. Bounded so the retry loop retries rather
    #: than blocking on a single long TCP timeout - the difference between a
    #: cold deploy recovering in seconds and appearing to hang.
    neo4j_connect_timeout_seconds: float = 8.0
    neo4j_connect_backoff_seconds: float = 1.5
    neo4j_connect_max_backoff_seconds: float = 10.0

    # Run the idempotent graph bootstrap during startup. Off only for tests
    # that supply their own graph.
    graph_bootstrap: bool = True

    # --- deployment ------------------------------------------------------
    # Cosmetic label for the Technical Details panel ("local" / "render").
    # Never used for behaviour - a deployment must not take a different code
    # path from the one that was evaluated.
    environment: str = "local"

    # --- llm ------------------------------------------------------------
    # "stub" is deterministic and offline: the app fully works with no API key.
    llm_provider: Literal["stub", "anthropic", "openai"] = "stub"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0

    # --- resolver thresholds -------------------------------------------
    # Calibrated by tests/test_resolver.py rather than treated as universal.
    fuzzy_accept_threshold: float = 0.88
    embedding_accept_threshold: float = 0.82

    # --- api ------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    #: The deployed frontend origin, appended to ``cors_origins``. Kept as its
    #: own variable so a deployment sets one obvious value instead of having to
    #: restate the local development origins.
    frontend_origin: str | None = None

    # --- mcp ------------------------------------------------------------
    # Mounted on the same FastAPI app; disabling it is a deployment choice,
    # not a code path change.
    mcp_enabled: bool = True
    # The MCP transport enables DNS-rebinding protection by default, which
    # validates the Host header and answers 421 to anything unlisted. That is
    # the right default for a server exposing member data, so it stays on and
    # the allow-list is configured rather than the protection disabled.
    # A deployment must add its public hostname here (e.g. via
    # MCP_ALLOWED_HOSTS='["future-coach-backend.onrender.com"]').
    mcp_allowed_hosts: list[str] = [
        "localhost",
        "localhost:8000",
        "127.0.0.1",
        "127.0.0.1:8000",
    ]
    mcp_allowed_origins: list[str] = []

    @property
    def bolt_uri(self) -> str:
        """The Bolt target, preferring a platform-supplied private hostname."""
        if self.neo4j_host:
            return f"bolt://{self.neo4j_host}:{self.neo4j_port}"
        return self.neo4j_uri

    @property
    def allowed_origins(self) -> list[str]:
        """CORS origins, including the deployed frontend when one is set.

        Never ``["*"]``: the API is served with credentials allowed, and a
        wildcard with credentials is both invalid and an invitation.
        """
        origins = list(self.cors_origins)
        origin = (self.frontend_origin or "").strip().rstrip("/")
        if origin:
            # Render's service reference yields a bare hostname, so a scheme is
            # added rather than requiring the operator to restate it (and get
            # it wrong).
            if "://" not in origin:
                origin = f"https://{origin}"
            if origin not in origins:
                origins.append(origin)
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
