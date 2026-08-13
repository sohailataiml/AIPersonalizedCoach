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
    neo4j_user: str = "neo4j"
    neo4j_password: str = "futurecoach"
    neo4j_database: str = "neo4j"

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

    # --- mcp ------------------------------------------------------------
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
