"""Composition root.

Built once at startup and shared. Which graph backend is active is decided here
and nowhere else - every consumer depends on the ``GraphRepository`` Protocol,
so switching between in-memory and Neo4j changes no safety code at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.agents.workout_graph import WorkoutWorkflow
from app.copilot.service import CopilotService
from app.core.config import Settings, get_settings
from app.graph.memory_repository import InMemoryGraphRepository
from app.graph.repository import GraphRepository
from app.llm.base import LLMClient
from app.llm.factory import build_llm_client
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

    def close(self) -> None:
        closer = getattr(self.repository, "close", None)
        if callable(closer):
            closer()


_services: Services | None = None


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or get_settings()
    ontology = get_ontology()
    repository, backend = _build_repository(settings, ontology)

    resolver = ConceptResolver.from_ontology(
        ontology,
        fuzzy_threshold=settings.fuzzy_accept_threshold,
        embedding_threshold=settings.embedding_accept_threshold,
    )
    engine = SafetyEngine(repository, ontology)
    llm = build_llm_client(settings)

    services = Services(
        settings=settings,
        ontology=ontology,
        repository=repository,
        resolver=resolver,
        engine=engine,
        llm=llm,
        workflow=WorkoutWorkflow(repository, ontology, resolver, engine, llm),
        copilot=CopilotService(llm),
        backend=backend,
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
    )
    return services


def _build_repository(settings: Settings, ontology: Ontology) -> tuple[GraphRepository, str]:
    if settings.graph_backend == "neo4j":
        try:
            from app.graph.neo4j_repository import Neo4jGraphRepository

            repository = Neo4jGraphRepository.connect(
                settings.neo4j_uri,
                settings.neo4j_user,
                settings.neo4j_password,
                settings.neo4j_database,
                settings.exercises_path,
                settings.member_context_path,
                ontology,
            )
            logger.info("graph backend: neo4j (%s)", settings.neo4j_uri)
            return repository, "neo4j"
        except Exception as exc:
            # Fall back so a missing database degrades DX, never correctness:
            # the in-memory backend runs the identical traversals.
            logger.warning(
                "Neo4j unavailable (%s); falling back to in-memory graph backend", exc
            )

    repository = InMemoryGraphRepository.from_files(
        settings.exercises_path, settings.member_context_path, ontology
    )
    logger.info("graph backend: memory")
    return repository, "memory"


def set_services(services: Services) -> None:
    global _services
    _services = services


def get_services() -> Services:
    if _services is None:  # pragma: no cover - startup guarantees this
        raise RuntimeError("Services not initialized")
    return _services
