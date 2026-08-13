"""Composition root.

Built once at startup and shared. Which graph backend is active is decided here
and nowhere else - every consumer depends on the ``GraphRepository`` Protocol,
so switching between in-memory and Neo4j changes no safety code at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agents.workout_graph import WorkoutWorkflow
from app.copilot.service import CopilotService
from app.core.config import Settings, get_settings
from app.graph.bootstrap import (
    SEED_VERSION,
    BootstrapReport,
    connect_with_retry,
    ensure_seeded,
    safe_target,
)
from app.graph.memory_repository import InMemoryGraphRepository
from app.graph.repository import GraphRepository
from app.llm.base import LLMClient
from app.llm.factory import build_llm_client
from app.member.trajectory import MemberTrajectoryService
from app.observability.collector import InstrumentedGraphRepository
from app.observability.store import TraceStore
from app.ontology.loader import Ontology, get_ontology
from app.resolution.resolver import ConceptResolver
from app.safety.engine import SafetyEngine

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    ontology: Ontology
    repository: GraphRepository
    resolver: ConceptResolver
    engine: SafetyEngine
    llm: LLMClient
    workflow: WorkoutWorkflow
    copilot: CopilotService
    backend: str
    # Optional so a hand-built container (tests) stays valid without it.
    trajectory: MemberTrajectoryService | None = None
    traces: TraceStore = field(default_factory=TraceStore)
    #: What startup found: reachability, seed state, verification problems.
    #: Readiness reports this rather than re-querying on every probe.
    bootstrap: BootstrapReport | None = None

    def close(self) -> None:
        closer = getattr(self.repository, "close", None)
        if callable(closer):
            closer()


_services: Services | None = None


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or get_settings()
    ontology = get_ontology()
    repository, backend, bootstrap = _build_repository(settings, ontology)
    # A counting pass-through, installed once. It delegates every call
    # untouched, so safety logic is unchanged by its presence - see
    # test_observability.py, which asserts identical decisions with and
    # without it.
    repository = InstrumentedGraphRepository(repository)

    resolver = ConceptResolver.from_ontology(
        ontology,
        fuzzy_threshold=settings.fuzzy_accept_threshold,
        embedding_threshold=settings.embedding_accept_threshold,
    )
    engine = SafetyEngine(repository, ontology)
    llm = build_llm_client(settings)
    # One longitudinal service for the whole process. The workout pipeline, the
    # Copilot and the MCP tools all read this instance, which is what makes
    # "the same trend everywhere" structural rather than a convention.
    trajectory_service = MemberTrajectoryService(ontology)

    services = Services(
        settings=settings,
        ontology=ontology,
        repository=repository,
        resolver=resolver,
        engine=engine,
        llm=llm,
        trajectory=trajectory_service,
        workflow=WorkoutWorkflow(
            repository, ontology, resolver, engine, llm, trajectory_service
        ),
        copilot=CopilotService(llm, trajectory_service=trajectory_service),
        backend=backend,
        bootstrap=bootstrap,
    )

    # The Copilot talks to MCP, which talks back to *this* container - so the
    # server is built with a provider closing over the object we just made.
    # Imported here rather than at module scope because app.mcp imports this
    # module for its Services type.
    from app.copilot.mcp_gateway import McpGateway
    from app.mcp.server import create_mcp_server

    copilot_server = create_mcp_server(services_provider=lambda: services)
    services.copilot = CopilotService(
        llm,
        gateway=McpGateway(copilot_server),
        catalog={e.name: e.id for e in repository.list_exercises()},
        trajectory_service=trajectory_service,
    )
    return services


def _build_repository(
    settings: Settings, ontology: Ontology
) -> tuple[GraphRepository, str, BootstrapReport | None]:
    """Build the configured repository. In neo4j mode there is no fallback.

    An earlier revision fell back to the in-memory backend when Neo4j was
    unreachable, on the grounds that both run identical traversals. That is
    true, and it is still the wrong behaviour for a deployment: silently
    swapping the storage engine underneath a *safety* system means an operator
    who asked for Neo4j gets something else and is never told. The service now
    reports itself unready instead, and says why.
    """
    if settings.graph_backend == "neo4j":
        repository, attempts = connect_with_retry(settings, ontology)
        report = (
            ensure_seeded(repository, settings)
            if settings.graph_bootstrap
            else BootstrapReport(backend="neo4j", reachable=True, seeded=True)
        )
        report.attempts = attempts
        logger.info(
            "graph backend: neo4j target=%s seeded=%s",
            safe_target(settings.bolt_uri),
            report.seeded,
        )
        return repository, "neo4j", report

    repository = InMemoryGraphRepository.from_files(
        settings.exercises_path, settings.member_context_path, ontology
    )
    logger.info("graph backend: memory")
    # The in-memory projection is built from the shipped data files, so it is
    # seeded by construction - there is nothing to bootstrap or to fail.
    return repository, "memory", BootstrapReport(
        backend="memory", reachable=True, seeded=True, seed_version=SEED_VERSION
    )


def set_services(services: Services) -> None:
    global _services
    _services = services


def get_services() -> Services:
    if _services is None:  # pragma: no cover - startup guarantees this
        raise RuntimeError("Services not initialized")
    return _services
