"""Service access for the MCP layer.

The whole point of this module is that it does **not** build anything. It hands
back the same ``Services`` container the FastAPI routes use, assembled once in
``app.api.deps.build_services`` and stored at application startup.

That is what keeps the architecture honest::

    Human UI  -> FastAPI REST -+
                               +-> the SAME resolver / engine / repository
    Copilot   -> MCP client   -+

If the MCP layer built its own resolver or engine, the two interfaces could
silently drift - different thresholds, a different graph backend - and the
deterministic safety guarantee would only hold on one of them.

The provider is injectable purely so tests can supply a container built against
the in-memory backend without starting the ASGI app. Production always uses
``get_services``.
"""

from __future__ import annotations

from collections.abc import Callable

from app.api.deps import Services, get_services

ServicesProvider = Callable[[], Services]

__all__ = ["ServicesProvider", "Services", "get_services"]
