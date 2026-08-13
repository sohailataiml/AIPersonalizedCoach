"""MCP-first Copilot tests.

The risk being managed is specific. A retrieval assistant that crashes is
obvious; one that answers fluently and wrongly is not. Adding a tool layer adds
two new ways to be fluently wrong:

* the model picks the wrong tool for a safety question, or none at all;
* the model receives a correct authoritative verdict and then talks around it.

The tests below pin both, plus the requirement that an MCP failure degrades to
the deterministic engine rather than to model opinion.
"""

from __future__ import annotations

import pytest

from app.api.deps import Services
from app.copilot.mcp_gateway import McpGateway, McpUnavailableError, ToolCall, ToolResult
from app.copilot.service import CopilotService
from app.copilot.tool_router import (
    MAX_TOOL_CALLS,
    SAFETY_TOOLS,
    SafetyVerdictGuard,
    plan_tools,
)
from app.core.config import get_settings
from app.llm.stub import StubLLMClient
from app.mcp.server import create_mcp_server

MEMBER_ID = "mbr_01HX9JORDAN"


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


class RecordingGateway(McpGateway):
    """Real gateway; records every call so we can assert MCP was truly used."""

    def __init__(self, server):
        super().__init__(server)
        self.calls: list[ToolCall] = []

    async def call_many(self, calls: list[ToolCall]) -> list[ToolResult]:
        self.calls.extend(calls)
        return await super().call_many(calls)


class BrokenGateway(McpGateway):
    def __init__(self):
        super().__init__(server=None)

    async def call_many(self, calls):
        raise McpUnavailableError("simulated MCP outage")


@pytest.fixture
def gateway(services: Services) -> RecordingGateway:
    return RecordingGateway(create_mcp_server(services_provider=lambda: services))


@pytest.fixture
def copilot(services: Services, gateway, catalog) -> CopilotService:
    return CopilotService(services.llm, gateway=gateway, catalog=catalog)


@pytest.fixture
def member(repository):
    return repository.get_member_context(MEMBER_ID)


# --- routing (1-4) -----------------------------------------------------------


class TestRouting:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("How has her adherence been trending?", "get_member_metric_trend"),
            ("How is she sleeping this week?", "get_member_metric_trend"),
            ("Can Jordan do Static Jump today?", "evaluate_exercise_safety"),
            ("Why was Barbell Decline Bench Press removed?", "get_exercise_provenance"),
            (
                "Give me safe quad-focused options for Jordan.",
                "get_safe_exercise_candidates",
            ),
        ],
    )
    async def test_question_routes_to_expected_tool(
        self, copilot: CopilotService, gateway, member, question, expected
    ):
        response = await copilot.answer(member, question)
        assert response.grounding.mode == "mcp"
        assert expected in response.grounding.tools_used, question

    async def test_reshaping_request_uses_authoritative_tools(
        self, copilot: CopilotService, member
    ):
        response = await copilot.answer(
            member,
            "Can you make this workout more quad-focused without aggravating her knee?",
        )
        used = set(response.grounding.tools_used)
        assert used & {"evaluate_workout_request", "get_safe_exercise_candidates"}
        assert response.grounding.authoritative_safety is True

    def test_safety_questions_always_plan_a_safety_tool(self, catalog):
        for question in [
            "Can Jordan do Static Jump today?",
            "Is Barbell Decline Bench Press safe for her?",
            "Why was Static Jump removed?",
            "What alternatives can she do instead?",
        ]:
            plan = plan_tools(question, MEMBER_ID, catalog)
            assert plan.touches_safety, question


# --- MCP is genuinely exercised (5) ------------------------------------------


class TestMcpIsActuallyUsed:
    async def test_tools_call_is_really_invoked(
        self, copilot: CopilotService, gateway, member
    ):
        await copilot.answer(member, "Can Jordan do Static Jump today?")
        assert gateway.calls, "the Copilot must go through MCP, not import tools.py"
        assert {c.name for c in gateway.calls} <= SAFETY_TOOLS | {
            "get_member_context",
            "get_member_metric_trend",
            "resolve_coach_concepts",
        }

    async def test_discovery_lists_all_seven(self, gateway):
        names = await gateway.list_tool_names()
        assert len(names) == 7

    async def test_result_is_structured_not_prose(self, gateway):
        results = await gateway.call_many(
            [ToolCall("get_member_metric_trend", {"member_id": MEMBER_ID, "metric": "adherence"})]
        )
        assert results[0].ok
        assert isinstance(results[0].payload, dict)
        assert results[0].payload["metric"] == "adherence"

    async def test_tool_error_is_a_failed_result_not_a_crash(self, gateway):
        results = await gateway.call_many(
            [ToolCall("get_member_metric_trend", {"member_id": MEMBER_ID, "metric": "vo2max"})]
        )
        assert results[0].ok is False
        assert results[0].error


# --- bounded loop (6) --------------------------------------------------------


class TestBoundedToolLoop:
    def test_plans_never_exceed_the_ceiling(self, catalog):
        questions = [
            "Can you make this workout more quad-focused without aggravating her knee?",
            "Why was Static Jump removed and what should she do instead?",
            "How is adherence, sleep, and can she squat?",
        ]
        for question in questions:
            assert len(plan_tools(question, MEMBER_ID, catalog).calls) <= MAX_TOOL_CALLS

    async def test_execution_is_bounded(self, copilot: CopilotService, gateway, member):
        await copilot.answer(
            member,
            "Can you make this workout more quad-focused without aggravating her knee?",
        )
        assert len(gateway.calls) <= MAX_TOOL_CALLS

    def test_ceiling_is_within_the_agreed_range(self):
        assert 3 <= MAX_TOOL_CALLS <= 5


# --- authoritative safety cannot be overridden (7) ---------------------------


class UnsafeLLM(StubLLMClient):
    """A model that tries to contradict the graph. The guard must win."""

    name = "unsafe-stub"

    async def answer_grounded(self, *, system, user, evidence, max_tokens=700) -> str:
        return "Yes, that is perfectly safe - she can do it, no problem at all."


class TestSafetyEnforcement:
    async def test_excluded_cannot_be_reported_as_safe(
        self, services: Services, gateway, catalog, member
    ):
        copilot = CopilotService(UnsafeLLM(), gateway=gateway, catalog=catalog)
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")

        lowered = response.answer.lower()
        assert "perfectly safe" not in lowered
        assert "excluded" in lowered
        assert response.grounding.safety_corrected is True

    def test_guard_rewrites_only_on_real_contradiction(self):
        excluded = [
            ToolResult(
                name="evaluate_exercise_safety",
                ok=True,
                payload={"exercise_name": "Static Jump", "status": "excluded"},
            )
        ]
        contradiction, corrected = SafetyVerdictGuard.enforce(
            "That is perfectly safe.", excluded
        )
        assert corrected is True
        assert "excluded" in contradiction.lower()

        neutral, untouched = SafetyVerdictGuard.enforce(
            "Static Jump is excluded because of her knee.", excluded
        )
        assert untouched is False
        assert neutral == "Static Jump is excluded because of her knee."

    def test_allowed_verdict_is_not_rewritten(self):
        allowed = [
            ToolResult(
                name="evaluate_exercise_safety",
                ok=True,
                payload={"exercise_name": "Goblet Squat", "status": "allowed"},
            )
        ]
        answer, corrected = SafetyVerdictGuard.enforce("That is safe.", allowed)
        assert corrected is False
        assert answer == "That is safe."


# --- fallback (8, 9, 10) -----------------------------------------------------


class TestFallback:
    async def test_mcp_failure_falls_back_to_deterministic_dispatcher(
        self, services: Services, catalog, member
    ):
        copilot = CopilotService(
            services.llm, gateway=BrokenGateway(), catalog=catalog
        )
        response = await copilot.answer(member, "How has her adherence been trending?")

        assert response.grounding.mode == "fallback"
        assert response.grounding.tools_used == []
        assert response.intent == "ADHERENCE_TREND"
        assert response.answer, "the fallback must still answer"

    async def test_safety_question_fails_closed_not_to_model_judgement(
        self, services: Services, catalog, member
    ):
        """An MCP outage must not produce free-form safety prose."""
        copilot = CopilotService(UnsafeLLM(), gateway=BrokenGateway(), catalog=catalog)
        response = await copilot.answer(member, "Can Jordan do Static Jump today?")

        assert response.grounding.mode == "fallback"
        assert response.grounding.authoritative_safety is False
        # The deterministic dispatcher answered from member-graph evidence; the
        # model never got to invent a safety verdict from nothing.
        assert response.evidence, "fallback answers are still evidence-backed"

    async def test_no_gateway_behaves_exactly_as_before(
        self, services: Services, member
    ):
        """The no-API-key, no-MCP demo path is unchanged."""
        copilot = CopilotService(services.llm)
        response = await copilot.answer(member, "How has her adherence been trending?")

        assert response.intent == "ADHERENCE_TREND"
        assert response.chart is not None
        assert response.citations
        assert response.grounding.mode == "fallback"

    async def test_stub_llm_still_works_end_to_end_over_mcp(
        self, copilot: CopilotService, member
    ):
        """No API key must still exercise the full MCP path."""
        response = await copilot.answer(member, "How has her adherence been trending?")
        assert response.grounding.mode == "mcp"
        assert response.answer
        assert response.chart is not None, "charts stay deterministic"
