"""Shared fixtures.

Tests run entirely against the in-memory graph repository. That is deliberate:
the highest-risk module in this system (the safety engine) must be testable
without Docker, a database, a network, or an API key, so it can be run on every
commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.intent import parse_intent
from app.domain.member import MemberContext
from app.graph.memory_repository import InMemoryGraphRepository
from app.ontology.loader import Ontology, get_ontology
from app.resolution.resolver import ConceptResolver
from app.safety.engine import SafetyContext, SafetyEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"

MEMBER_ID = "mbr_01HX9JORDAN"


@pytest.fixture(scope="session")
def ontology() -> Ontology:
    return get_ontology()


@pytest.fixture(scope="session")
def repository() -> InMemoryGraphRepository:
    return InMemoryGraphRepository.from_files(
        DATA / "exercises.json", DATA / "member-context.json"
    )


@pytest.fixture(scope="session")
def resolver(ontology: Ontology) -> ConceptResolver:
    return ConceptResolver.from_ontology(ontology)


@pytest.fixture
def member(repository: InMemoryGraphRepository) -> MemberContext:
    context = repository.get_member_context(MEMBER_ID)
    assert context is not None
    return context


@pytest.fixture
def engine(repository: InMemoryGraphRepository, ontology: Ontology) -> SafetyEngine:
    return SafetyEngine(repository, ontology)


@pytest.fixture
def evaluate(engine: SafetyEngine, resolver: ConceptResolver, member: MemberContext):
    """Run the full deterministic path for a coach prompt.

    Returns ``(decisions_by_id, context)``.
    """

    def _run(prompt: str, duration: int = 45):
        intent, resolved = parse_intent(prompt, duration, resolver)
        context: SafetyContext = engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}
        return decisions, context

    return _run


def by_name(repository: InMemoryGraphRepository, name: str) -> str:
    """Look up an exercise id by exact display name."""
    for exercise in repository.list_exercises():
        if exercise.name == name:
            return exercise.id
    raise AssertionError(f"exercise not found in catalog: {name}")
