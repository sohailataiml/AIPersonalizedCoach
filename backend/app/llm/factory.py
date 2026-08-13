"""Provider selection.

Falls back to the deterministic stub whenever the configured provider has no
credentials, so a missing key degrades the *prose quality* and never the safety
behaviour.
"""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.llm.base import LLMClient
from app.llm.providers import AnthropicClient, OpenAIClient
from app.llm.stub import StubLLMClient

logger = logging.getLogger(__name__)


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    provider = settings.llm_provider

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning("llm_provider=anthropic but ANTHROPIC_API_KEY is unset; using stub")
            return StubLLMClient()
        return AnthropicClient(
            settings.anthropic_api_key, settings.anthropic_model, settings.llm_timeout_seconds
        )

    if provider == "openai":
        if not settings.openai_api_key:
            logger.warning("llm_provider=openai but OPENAI_API_KEY is unset; using stub")
            return StubLLMClient()
        return OpenAIClient(
            settings.openai_api_key, settings.openai_model, settings.llm_timeout_seconds
        )

    return StubLLMClient()
