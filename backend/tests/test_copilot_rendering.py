"""The visible answer must be prose, never a payload.

The bug these pin: the MCP path built its evidence dict keyed by tool name, so
it carried no top-level ``summary``. The offline stub - which is what the
deployed demo runs - fell through to its key/value branch and rendered nested
dicts with ``str()``. The coach saw six kilobytes of Python dict repr where a
sentence belonged.

Nothing about the verdict was wrong. Only its presentation was, which is why
every assertion here is about *rendering* and none of them touch the safety
engine.
"""

from __future__ import annotations

import pytest

from app.api.deps import Services
from app.copilot.mcp_gateway import McpGateway, McpUnavailableError, ToolResult
from app.copilot.mcp_narrator import (
    build_safety_evidence,
    looks_like_raw_payload,
    narrate,
)
from app.copilot.service import CopilotService
from app.core.config import get_settings
from app.llm.base import LLMError
from app.llm.stub import StubLLMClient
from app.mcp.server import create_mcp_server

MEMBER_ID = "mbr_01HX9JORDAN"

#: Substrings that only ever appear in a serialized payload, never in a
#: sentence a coach should read.
PAYLOAD_MARKERS = (
    "{'member_id'",
    '"member_id"',
    "member_id",
    "exercise_id",
    "graph_paths",
    "rule_ids",
    "is_excluded",
    "{'",
    '{"',
)


@pytest.fixture
def services(repository, ontology, resolver, engine) -> Services:
    return Services(
        settings=get_settings(),
        ontology=ontology,
        repository=repository,
        resolver=resolver,
        engine=engine,
        llm=StubLLMClient(),
        workflow=None,
        copilot=None,
        backend="memory",
    )


@pytest.fixture
def catalog(repository) -> dict[str, str]:
    return {e.name: e.id for e in repository.list_exercises()}


@pytest.fixture
def gateway(services: Services) -> McpGateway:
    return McpGateway(create_mcp_server(services_provider=lambda: services))


@pytest.fixture
def copilot(services: Services, gateway, catalog) -> CopilotService:
    return CopilotService(services.llm, gateway=gateway, catalog=catalog)


@pytest.fixture
def member(repository):
    return repository.get_member_context(MEMBER_ID)


SAFETY_QUESTIONS = [
    "Can Jordan do Static Jump today?",
    "Why was Static Jump removed?",
    "Is Barbell Decline Bench Press safe for her?",
    "Give me safe quad-focused options for Jordan.",
    "How has her adherence been trending?",
]


class TestAnswerIsProse:
    @pytest.mark.parametrize("question", SAFETY_QUESTIONS)
    async def test_answer_contains_no_serialized_payload(
        self, copilot: CopilotService, member, question
    ):
        response = await copilot.answer(member, question)
        for marker in PAYLOAD_MARKERS:
            assert marker not in response.answer, (
                f"{question!r} leaked {marker!r} into the visible answer"
            )

    @pytest.mark.parametrize("question", SAFETY_QUESTIONS)
    async def test_answer_is_short_and_readable(
        self, copilot: CopilotService, member, question
    ):
        response = await copilot.answer(member, question)
        assert response.answer.strip(), "the visible answer must not be empty"
        # The pre-fix answer for the first question was 6177 characters.
        assert len(response.answer) < 900, f"answer is a dump, not a summary: {question}"
        assert response.answer.rstrip().endswith((".", "!", "?"))

    async def test_safety_question_states_the_verdict(
        self, copilot: CopilotService, member
    ):
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")
        lowered = response.answer.lower()

        assert "static jump" in lowered
        assert "excluded" in lowered
        # The reason is graph-derived, and the exercise's own name for it.
        assert "patellofemoral" in lowered

    async def test_provenance_question_explains_without_dumping(
        self, copilot: CopilotService, member
    ):
        response = await copilot.answer(member, "Why was Static Jump removed?")
        lowered = response.answer.lower()

        assert "static jump" in lowered
        assert "graph" in lowered or "removed" in lowered
        assert "-[" not in response.answer, "raw traversal syntax belongs in evidence"


class TestGroundingMetadataSurvives:
    async def test_mode_tools_and_authority_are_reported(
        self, copilot: CopilotService, member
    ):
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")
        grounding = response.grounding

        assert grounding is not None
        assert grounding.mode == "mcp"
        assert "evaluate_exercise_safety" in grounding.tools_used
        assert "get_exercise_provenance" in grounding.tools_used
        assert grounding.authoritative_safety is True

    async def test_structured_payloads_are_still_returned_separately(
        self, copilot: CopilotService, member
    ):
        """The raw results stay available - just not as the answer."""
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")

        assert "evaluate_exercise_safety" in response.evidence
        assert response.evidence["evaluate_exercise_safety"]["status"] == "excluded"


class TestSafetyEvidenceProjection:
    async def test_evidence_is_display_ready(self, copilot: CopilotService, member):
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")
        evidence = response.safety_evidence

        assert evidence is not None
        assert evidence.exercise_name == "Static Jump"
        assert evidence.decision == "excluded"
        assert evidence.rule_ids, "the rules that fired must be nameable"
        assert evidence.reasons and all(r.message for r in evidence.reasons)

    async def test_graph_paths_are_real_rendered_traversals(
        self, copilot: CopilotService, member
    ):
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")
        paths = response.safety_evidence.graph_paths

        assert paths, "an excluded verdict from a traversal must show the traversal"
        # Rendered by the graph engine; the shape proves it was not written here.
        assert all("-[" in path and "]->" in path for path in paths)

    async def test_absent_for_non_safety_questions(
        self, copilot: CopilotService, member
    ):
        response = await copilot.answer(member, "How has her adherence been trending?")
        assert response.safety_evidence is None


class BrokenLLM(StubLLMClient):
    """A provider that is configured but failing."""

    name = "broken"

    async def answer_grounded(self, *, system, user, evidence, max_tokens=700) -> str:
        raise LLMError("provider unreachable")


class EchoingLLM(StubLLMClient):
    """A provider that hands its evidence straight back - the original bug."""

    name = "echo"

    async def answer_grounded(self, *, system, user, evidence, max_tokens=700) -> str:
        return evidence


class EmptyLLM(StubLLMClient):
    name = "empty"

    async def answer_grounded(self, *, system, user, evidence, max_tokens=700) -> str:
        return "   "


class TestDegradedProviders:
    """Whatever the provider does, the coach gets sentences."""

    @pytest.mark.parametrize("llm", [BrokenLLM(), EchoingLLM(), EmptyLLM()])
    async def test_unusable_provider_output_becomes_deterministic_prose(
        self, gateway, catalog, member, llm
    ):
        copilot = CopilotService(llm, gateway=gateway, catalog=catalog)
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")

        assert response.answer.strip()
        for marker in PAYLOAD_MARKERS:
            assert marker not in response.answer
        assert "static jump" in response.answer.lower()
        assert "excluded" in response.answer.lower()
        # Still authoritative: the verdict came from the graph either way.
        assert response.grounding.authoritative_safety is True

    async def test_offline_stub_answer_is_evidence_backed(
        self, copilot: CopilotService, member
    ):
        """The no-API-key path must not degrade to a generic apology."""
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")

        assert response.generator == "stub"
        assert "unable to generate" not in response.answer.lower()
        assert response.safety_evidence is not None


class TestNarratorUnit:
    def test_narration_never_trips_its_own_leak_check(self, gateway):
        """A false positive here would blank a perfectly good answer."""
        results = [
            ToolResult(
                name="evaluate_exercise_safety",
                ok=True,
                payload={
                    "exercise_name": "Static Jump",
                    "status": "excluded",
                    "reasons": [
                        {
                            "rule_id": "injury_contraindicated_pattern",
                            "message": "PFPS contraindicates the 'cardio - plyometric' pattern.",
                            "evidence": ["A -[CONTRAINDICATES]-> B"],
                        }
                    ],
                },
            )
        ]
        assert not looks_like_raw_payload(narrate(results, "Jordan"))

    @pytest.mark.parametrize(
        "text",
        [
            "{'member_id': 'mbr_1'}",
            '{"exercise_id": "x"}',
            "evaluate exercise safety: {'status': 'excluded'}",
            "[{'a': 1}]",
        ],
    )
    def test_payloads_are_detected(self, text):
        assert looks_like_raw_payload(text)

    @pytest.mark.parametrize(
        "text",
        [
            "No - Static Jump is excluded for Jordan by the safety engine.",
            "Jordan's adherence moved from 100% to 50% across 4 observations.",
            "",
        ],
    )
    def test_prose_is_not_flagged(self, text):
        assert not looks_like_raw_payload(text)

    def test_failed_results_are_not_narrated(self):
        results = [ToolResult(name="evaluate_exercise_safety", ok=False, error="boom")]
        narrative = narrate(results, "Jordan")

        assert narrative.strip()
        assert not looks_like_raw_payload(narrative)
        assert build_safety_evidence(results) is None

    def test_allowed_verdict_reads_as_a_yes(self):
        results = [
            ToolResult(
                name="evaluate_exercise_safety",
                ok=True,
                payload={"exercise_name": "Goblet Squat", "status": "allowed"},
            )
        ]
        assert "yes" in narrate(results, "Jordan").lower()

    def test_narrator_reports_status_it_does_not_decide_it(self):
        """Feed it a status the engine would never produce; it must not editorialise."""
        results = [
            ToolResult(
                name="evaluate_exercise_safety",
                ok=True,
                payload={"exercise_name": "Test Move", "status": "downranked"},
            )
        ]
        narrative = narrate(results, "Jordan").lower()
        assert "ranks it down" in narrative
        assert "excluded" not in narrative


class TestGuardStillWins:
    async def test_correction_survives_the_new_formatting_path(
        self, gateway, catalog, member
    ):
        class UnsafeLLM(StubLLMClient):
            name = "unsafe"

            async def answer_grounded(self, *, system, user, evidence, max_tokens=700):
                return "Yes, that is perfectly safe - no problem at all."

        copilot = CopilotService(UnsafeLLM(), gateway=gateway, catalog=catalog)
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")

        assert "perfectly safe" not in response.answer.lower()
        assert "excluded" in response.answer.lower()
        assert response.grounding.safety_corrected is True

    async def test_deterministic_narration_is_not_mistaken_for_a_contradiction(
        self, copilot: CopilotService, member
    ):
        """The narrator's own wording must not trip the guard."""
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")
        assert response.grounding.safety_corrected is False


class TestFallbackPathUnchanged:
    async def test_dispatcher_fallback_still_reads_well(
        self, services: Services, catalog, member
    ):
        class BrokenGateway(McpGateway):
            def __init__(self):
                super().__init__(server=None)

            async def call_many(self, calls):
                raise McpUnavailableError("simulated outage")

        copilot = CopilotService(
            services.llm, gateway=BrokenGateway(), catalog=catalog
        )
        response = await copilot.answer(member, "How has her adherence been trending?")

        assert response.grounding.mode == "fallback"
        assert response.answer.strip()
        for marker in PAYLOAD_MARKERS:
            assert marker not in response.answer
