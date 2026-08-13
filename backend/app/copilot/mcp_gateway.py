"""The Copilot's MCP client.

This is a **real MCP client session**, not a shortcut. It performs discovery
(``tools/list``) and invocation (``tools/call``) over the protocol, so schema
validation, structured results and protocol-level errors are all exercised
exactly as they would be for an external client.

The transport is in-process (``InMemoryTransport``) rather than HTTP. That is a
transport choice, not a protocol shortcut: the same ``MCPServer`` object serves
both, external clients reach it over Streamable HTTP at ``/mcp``, and no network
hop is added to a request the coach is waiting on.

Deliberately absent: any import of ``app.mcp.tools``. Calling the tool functions
directly would bypass the very layer this integration exists to prove.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from mcp.client._memory import InMemoryTransport
from mcp.client.client import Client

logger = logging.getLogger(__name__)


class McpUnavailableError(RuntimeError):
    """The MCP layer could not be reached or returned a protocol error."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    name: str
    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class McpGateway:
    """Discovers and invokes MCP tools on behalf of the Copilot."""

    def __init__(self, server: Any) -> None:
        self._server = server

    def _client(self) -> Client:
        return Client(InMemoryTransport(self._server))

    async def list_tool_names(self) -> list[str]:
        try:
            async with self._client() as client:
                return [t.name for t in (await client.list_tools()).tools]
        except Exception as exc:  # pragma: no cover - defensive
            raise McpUnavailableError(f"tools/list failed: {exc}") from exc

    async def call(self, call: ToolCall) -> ToolResult:
        """Invoke one tool. Protocol errors become a failed ToolResult, not a raise.

        A tool erroring is an expected outcome the caller must be able to reason
        about (and, for safety questions, fail closed on). Only a transport-level
        failure raises.
        """
        try:
            async with self._client() as client:
                result = await client.call_tool(call.name, call.arguments)
        except Exception as exc:
            raise McpUnavailableError(f"tools/call {call.name} failed: {exc}") from exc

        if result.is_error:
            message = ""
            if result.content:
                message = getattr(result.content[0], "text", "") or ""
            logger.warning("mcp tool error name=%s detail=%s", call.name, message[:200])
            return ToolResult(name=call.name, ok=False, error=message or "tool error")

        return ToolResult(
            name=call.name, ok=True, payload=dict(result.structured_content or {})
        )

    async def call_many(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Run a bounded plan, stopping at the first transport failure."""
        results: list[ToolResult] = []
        async with self._client() as client:
            for call in calls:
                try:
                    raw = await client.call_tool(call.name, call.arguments)
                except Exception as exc:
                    raise McpUnavailableError(
                        f"tools/call {call.name} failed: {exc}"
                    ) from exc

                if raw.is_error:
                    detail = ""
                    if raw.content:
                        detail = getattr(raw.content[0], "text", "") or ""
                    results.append(
                        ToolResult(name=call.name, ok=False, error=detail or "tool error")
                    )
                else:
                    results.append(
                        ToolResult(
                            name=call.name,
                            ok=True,
                            payload=dict(raw.structured_content or {}),
                        )
                    )
        return results
