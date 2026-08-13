"""MCP interface layer.

An AI-facing adapter over the existing application services. It is one of two
interfaces onto the same domain, not a second implementation of it::

    Human UI -> FastAPI REST -+
                              +-> resolver / safety engine / graph repository
    Copilot  -> MCP client   -+

No safety logic lives in this package.
"""

from __future__ import annotations

from app.mcp.server import (
    SERVER_NAME,
    create_mcp_server,
    mcp_asgi_app,
    mcp_server,
    mcp_session_lifespan,
)

__all__ = [
    "SERVER_NAME",
    "create_mcp_server",
    "mcp_asgi_app",
    "mcp_server",
    "mcp_session_lifespan",
]
