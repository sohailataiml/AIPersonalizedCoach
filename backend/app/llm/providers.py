"""Anthropic and OpenAI clients behind the shared LLMClient Protocol.

Both use plain httpx rather than a vendor SDK so the dependency surface stays
small and the request shape is visible in review. Structured output is requested
via a JSON schema tool / response_format and then validated with Pydantic - if
validation fails we raise rather than passing unvalidated output downstream.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError

T = TypeVar("T", bound=BaseModel)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def generate_structured(
        self, *, schema: type[T], system: str, user: str, max_tokens: int = 2000
    ) -> T:
        tool = {
            "name": "emit_result",
            "description": f"Return a {schema.__name__} object.",
            "input_schema": schema.model_json_schema(),
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": "emit_result"},
        }
        data = await self._post(payload)

        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return _validate(schema, block.get("input", {}))
        raise LLMError("Anthropic response contained no tool_use block")

    async def answer_grounded(
        self, *, system: str, user: str, evidence: str, max_tokens: int = 700
    ) -> str:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [
                {"role": "user", "content": f"{user}\n\n<evidence>\n{evidence}\n</evidence>"}
            ],
        }
        data = await self._post(payload)
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(parts).strip()

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        return await _request(ANTHROPIC_URL, headers, payload, self._timeout)


class OpenAIClient:
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def generate_structured(
        self, *, schema: type[T], system: str, user: str, max_tokens: int = 2000
    ) -> T:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": _openai_strict_schema(schema),
                    "strict": False,
                },
            },
        }
        data = await self._post(payload)
        content = data["choices"][0]["message"]["content"]
        try:
            return _validate(schema, json.loads(content))
        except (ValueError, KeyError) as exc:
            raise LLMError(f"OpenAI returned unparseable JSON: {exc}") from exc

    async def answer_grounded(
        self, *, system: str, user: str, evidence: str, max_tokens: int = 700
    ) -> str:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{user}\n\n<evidence>\n{evidence}\n</evidence>"},
            ],
        }
        data = await self._post(payload)
        return (data["choices"][0]["message"]["content"] or "").strip()

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }
        return await _request(OPENAI_URL, headers, payload, self._timeout)


async def _request(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        # Never echo the request body: it can contain member context.
        raise LLMError(f"LLM provider returned {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM provider request failed: {type(exc).__name__}") from exc


def _validate(schema: type[T], data: Any) -> T:
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"LLM output failed {schema.__name__} validation: {exc}") from exc


def _openai_strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """OpenAI rejects $defs-heavy schemas in some modes; inline what we can."""
    raw = schema.model_json_schema()
    raw.setdefault("additionalProperties", False)
    return raw
