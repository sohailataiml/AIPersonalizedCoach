"""The MCP server: registration and transport.

Design notes for a reviewer
---------------------------

**Which SDK API.** The official ``mcp`` SDK moved its high-level server API in
2.0: ``mcp.server.fastmcp.FastMCP`` no longer exists and is replaced by
``mcp.server.mcpserver.MCPServer``. ``MCPServer`` derives both the input *and*
the output JSON Schema from the annotations on each tool function, so the
Pydantic models in ``schemas.py`` are the published contract rather than a
description of one.

**Transport.** Streamable HTTP, mounted into the existing FastAPI app at
``/mcp``. Mounting was chosen over a sibling process because it needs no second
port, no second deployment target on Render, and - the real reason - it
guarantees the MCP tools and the REST routes observe the *same* process-local
``Services`` container. A sibling process would have its own graph backend
connection and could drift.

``stateless_http=True`` is deliberate. Every tool here is a pure read over
graph-derived state, so there is no session to keep. Stateless mode avoids
running the session manager's task group inside FastAPI's lifespan, which is the
awkward lifecycle issue the mounting approach would otherwise introduce.

**What is NOT here.** No rule evaluation, no traversal, no thresholds. Each
registered function is a thin binding onto ``app.mcp.tools``, which in turn
delegates to the same services the REST API uses.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.core.config import get_settings
from app.mcp import tools
from app.mcp.dependencies import ServicesProvider, get_services
from app.mcp.schemas import (
    ExerciseProvenanceResult,
    ExerciseSafetyResult,
    MemberContextView,
    MetricTrendResult,
    ResolveConceptsResult,
    SafeCandidatesResult,
    WorkoutRequestEvaluation,
)

logger = logging.getLogger(__name__)

SERVER_NAME = "future-coach"

INSTRUCTIONS = """Tools over a coach intelligence platform for ONE synthetic member.

Authority model - this is not advisory:

* The knowledge graph and the deterministic safety engine decide exercise
  safety. You do not. Never infer that an exercise is safe or unsafe from a
  member's injury list or equipment; call `evaluate_workout_request` and report
  what it returns.
* `evaluate_workout_request` is read-only. It evaluates and ranks, but never
  composes a workout. Plan generation lives behind the REST API.
* Every exclusion carries graph evidence. When explaining a removal, cite that
  evidence rather than paraphrasing a guess.
* If a concept does not resolve, say so. Do not substitute a nearby concept.
"""


def create_mcp_server(
    services_provider: ServicesProvider = get_services,
) -> MCPServer:
    """Build the MCP server.

    ``services_provider`` is resolved lazily *per call*, not at build time: the
    server is constructed when the module is imported, whereas the services
    container is assembled during FastAPI's lifespan startup. Late binding also
    lets tests point the same server at an in-memory container.
    """
    server = MCPServer(
        name=SERVER_NAME,
        title="Future Coach Intelligence Platform",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )

    @server.tool(
        name="get_member_context",
        description=(
            "Compact profile for one member: goals, preferences, injuries, "
            "equipment, adherence and sleep trends, biomarkers, coach brief and "
            "churn indicators. Context for explanation only - it does not "
            "establish exercise safety."
        ),
    )
    def get_member_context(member_id: str) -> MemberContextView:
        return tools.get_member_context(services_provider(), member_id)

    @server.tool(
        name="resolve_coach_concepts",
        description=(
            "Map coach free text onto canonical graph concepts (anatomy, "
            "equipment, movement families, muscles, injury conditions). Returns "
            "the resolution method and confidence for each phrase, and reports "
            "phrases that resolved to nothing instead of guessing."
        ),
    )
    def resolve_coach_concepts(
        text: str, duration_minutes: int = 45
    ) -> ResolveConceptsResult:
        return tools.resolve_coach_concepts(services_provider(), text, duration_minutes)

    @server.tool(
        name="get_member_metric_trend",
        description=(
            "Deterministic trend for one member metric: 'adherence', 'sleep' or "
            "'weight'. Returns real observations plus first/latest values, "
            "absolute and percent delta, and a direction. All arithmetic is "
            "computed in Python - report these numbers, do not recalculate them. "
            "An unsupported metric is an error rather than an empty result."
        ),
    )
    def get_member_metric_trend(
        member_id: str, metric: str, window: int | None = None
    ) -> MetricTrendResult:
        return tools.get_member_metric_trend(
            services_provider(), member_id, metric, window
        )

    @server.tool(
        name="evaluate_exercise_safety",
        description=(
            "Use this tool whenever a coach asks whether an exercise is safe, "
            "contraindicated, injury-compatible, or equipment-compatible for a "
            "member. The deterministic result is authoritative and must not be "
            "overridden by model judgment. Returns status "
            "(allowed/downranked/excluded) with the rules, injury evidence, "
            "equipment analysis and graph traversals that produced it."
        ),
    )
    def evaluate_exercise_safety(
        member_id: str, exercise_id: str, prompt: str = ""
    ) -> ExerciseSafetyResult:
        return tools.evaluate_exercise_safety(
            services_provider(), member_id, exercise_id, prompt
        )

    @server.tool(
        name="get_exercise_provenance",
        description=(
            "Explain WHY the deterministic engine reached a decision about an "
            "exercise for a member. Returns the real graph paths - ordered nodes, "
            "relationships and directions - plus injury, anatomy and equipment "
            "evidence. When a decision rests on a set operation rather than a "
            "traversal, has_graph_path is false and the real basis is stated. "
            "Never invent a graph path; report what this tool returns."
        ),
    )
    def get_exercise_provenance(
        member_id: str, exercise_id: str, prompt: str = ""
    ) -> ExerciseProvenanceResult:
        return tools.get_exercise_provenance(
            services_provider(), member_id, exercise_id, prompt
        )

    @server.tool(
        name="get_safe_exercise_candidates",
        description=(
            "Use this tool before suggesting exercise alternatives for a member. "
            "Only suggest exercises from the graph-approved candidate set "
            "returned by this tool. Accepts optional focus, equipment, "
            "exclusions and injury mentions; returns ranked eligible and "
            "downranked candidates with counts. Excluded exercises are never "
            "included."
        ),
    )
    def get_safe_exercise_candidates(
        member_id: str,
        focus: list[str] | None = None,
        equipment: list[str] | None = None,
        exclusions: list[str] | None = None,
        injury_mentions: list[str] | None = None,
        preferences: list[str] | None = None,
        limit: int = 20,
    ) -> SafeCandidatesResult:
        return tools.get_safe_exercise_candidates(
            services_provider(),
            member_id,
            focus=focus,
            equipment=equipment,
            exclusions=exclusions,
            injury_mentions=injury_mentions,
            preferences=preferences,
            limit=limit,
        )

    @server.tool(
        name="evaluate_workout_request",
        description=(
            "Deterministic, READ-ONLY safety evaluation of a workout request. "
            "Runs intent parsing, concept resolution, graph safety evaluation and "
            "ranking, then stops. Returns eligible, downranked and excluded "
            "exercises with graph evidence and counts. Use this to answer "
            "'would this be safe', 'what constraints apply', 'what is eligible' "
            "and 'why was X removed'. It does NOT compose a workout."
        ),
    )
    def evaluate_workout_request(
        member_id: str, prompt: str, duration_minutes: int = 45
    ) -> WorkoutRequestEvaluation:
        return tools.evaluate_workout_request(
            services_provider(), member_id, prompt, duration_minutes
        )

    logger.info("mcp server built name=%s", SERVER_NAME)
    return server


mcp_server = create_mcp_server()

_asgi_app = None


def mcp_asgi_app(path: str = "/"):
    """The mountable Streamable-HTTP ASGI app for the module-level server.

    Cached, because ``streamable_http_app()`` lazily constructs the session
    manager and calling it twice would produce a second one - leaving the mounted
    app and the running lifecycle attached to different managers.
    """
    global _asgi_app
    if _asgi_app is None:
        settings = get_settings()
        _asgi_app = mcp_server.streamable_http_app(
            streamable_http_path=path,
            stateless_http=True,
            # DNS-rebinding protection stays ON. This server exposes member
            # health data, so an allow-list is configured rather than the
            # protection switched off; unlisted hosts get a 421.
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=list(settings.mcp_allowed_hosts),
                allowed_origins=list(settings.mcp_allowed_origins),
            ),
        )
    return _asgi_app


@asynccontextmanager
async def mcp_session_lifespan() -> AsyncIterator[None]:
    """Run the MCP session manager for the lifetime of the host application.

    This is required, and the failure it prevents is not obvious: Starlette's
    ``Mount`` does **not** run a sub-application's lifespan. Mounting the MCP app
    alone therefore yields an app that imports, starts and serves REST traffic
    happily, then fails on the first MCP request with "Task group is not
    initialized" - a runtime-only error that no import check would catch.

    Binding the manager to the host lifespan is what makes mounting viable
    instead of forcing a sibling process.
    """
    mcp_asgi_app()  # ensure the session manager has been constructed
    async with mcp_server.session_manager.run():
        yield
