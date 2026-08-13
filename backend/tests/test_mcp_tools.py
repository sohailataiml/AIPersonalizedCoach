"""MCP interface-layer tests.

Two properties are being protected here, and they are different:

1. **The adapter reports what the engine decided.** An MCP tool that quietly
   disagreed with ``SafetyEngine`` would be worse than no tool at all, because
   it would look authoritative. Several tests below re-run the deterministic
   pipeline directly and assert the tool's answer is identical.

2. **The MCP surface is real.** Tools are exercised through an actual
   ``Client`` session over an in-memory transport, not by calling the Python
   functions, so schema generation, argument validation and error semantics are
   covered rather than assumed.
"""

from __future__ import annotations

import pytest
from mcp.client._memory import InMemoryTransport
from mcp.client.client import Client

from app.agents.intent import parse_intent
from app.api.deps import Services
from app.core.config import get_settings
from app.llm.stub import StubLLMClient
from app.mcp import tools
from app.mcp.server import create_mcp_server
from app.safety.ranking import rank_candidates

MEMBER_ID = "mbr_01HX9JORDAN"
INJURY_PROMPT = "Create a 45-minute lower-body workout. Her left knee is bothering her."


@pytest.fixture
def services(repository, ontology, resolver, engine) -> Services:
    """A Services container over the in-memory backend.

    Deliberately assembled from the same fixtures the safety tests use, so an
    MCP test and a safety test are reasoning about one identical graph.
    """
    return Services(
        settings=get_settings(),
        ontology=ontology,
        repository=repository,
        resolver=resolver,
        engine=engine,
        llm=StubLLMClient(),
        workflow=None,  # not needed: no MCP tool composes a workout
        copilot=None,
        backend="memory",
    )


@pytest.fixture
def mcp_client(services: Services):
    server = create_mcp_server(services_provider=lambda: services)
    return Client(InMemoryTransport(server))


# --- tool 1 ------------------------------------------------------------------


class TestGetMemberContext:
    def test_returns_projection_not_raw_dump(self, services: Services):
        view = tools.get_member_context(services, MEMBER_ID)

        assert view.member_id == MEMBER_ID
        assert view.name
        assert view.goals and view.goals[0].priority <= view.goals[-1].priority
        assert view.injuries, "the synthetic member has a recorded injury"
        assert view.equipment_available

        # Chat transcripts and raw ingestion structures must not leak through.
        assert not hasattr(view, "chat_history")
        assert not hasattr(view, "workout_history")

    def test_absent_data_is_null_not_fabricated(self, services: Services):
        view = tools.get_member_context(services, MEMBER_ID)
        biomarkers = view.biomarkers.model_dump()
        # Every biomarker is either genuinely present or explicitly None - never
        # a filled-in zero, which a model would read as a real observation.
        for key, value in biomarkers.items():
            assert value is None or isinstance(value, int | float | str), key

    def test_matches_rest_single_member_fallback(self, services: Services):
        """MCP must not be stricter than REST, or the interfaces diverge.

        ``GraphRepository.get_member_context`` deliberately resolves *any* id
        when the dataset holds a single member (memory_repository.py:80), and the
        REST route inherits that. Adding an id check here would make the same
        request succeed over HTTP and fail over MCP, which is exactly the drift
        the shared-services rule exists to prevent.
        """
        assert (
            tools.get_member_context(services, "mbr_anything").member_id == MEMBER_ID
        )

    def test_missing_member_raises(self, services: Services, monkeypatch):
        """The not-found path is real, just unreachable with one-member data."""
        monkeypatch.setattr(
            services.repository, "get_member_context", lambda _member_id: None
        )
        with pytest.raises(tools.MemberNotFoundError):
            tools.get_member_context(services, "mbr_does_not_exist")


# --- tool 2 ------------------------------------------------------------------


class TestResolveCoachConcepts:
    def test_resolves_the_documented_phrases(self, services: Services):
        result = tools.resolve_coach_concepts(
            services, "Her left knee is bothering her and she only has dumbbells."
        )
        by_id = {c.canonical_id: c for c in result.concepts}

        assert "anatomy:knee" in by_id
        assert "equipment:dumbbell" in by_id
        # Pass 1 handles both; method must be reported truthfully.
        assert by_id["anatomy:knee"].method in {"exact", "alias"}
        assert by_id["equipment:dumbbell"].confidence >= 0.9

    def test_matches_what_the_pipeline_would_see(self, services: Services):
        """The tool must not diverge from the resolution the engine receives."""
        result = tools.resolve_coach_concepts(services, INJURY_PROMPT)
        _, resolved = parse_intent(INJURY_PROMPT, 45, services.resolver)

        assert {c.canonical_id for c in result.concepts} == {
            c.canonical_id for c in resolved if c.is_resolved
        }

    def test_unresolved_is_reported_not_dropped(self, services: Services):
        result = tools.resolve_coach_concepts(
            services, "Her thingy feels weird and sore."
        )
        assert result.unresolved, "a clinical-sounding miss must stay visible"
        assert all(c.canonical_id is None for c in result.unresolved)


# --- tool 7 ------------------------------------------------------------------


class TestEvaluateWorkoutRequest:
    def test_is_read_only_and_composes_nothing(self, services: Services):
        result = tools.evaluate_workout_request(services, MEMBER_ID, INJURY_PROMPT)
        assert result.composed_workout is None
        assert result.graph_reasoning.summary.catalog_count > 0

    def test_agrees_exactly_with_the_safety_engine(self, services: Services):
        """The whole contract: the tool reports, the engine decides."""
        result = tools.evaluate_workout_request(services, MEMBER_ID, INJURY_PROMPT)

        member = services.repository.get_member_context(MEMBER_ID)
        intent, resolved = parse_intent(INJURY_PROMPT, 45, services.resolver)
        context = services.engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in services.engine.evaluate_all(context)}
        candidates = rank_candidates(
            services.repository.list_exercises(),
            decisions,
            member,
            intent,
            resolved,
            services.ontology,
        )

        assert {e.exercise_id for e in result.excluded} == {
            d.exercise_id for d in decisions.values() if d.is_excluded
        }
        assert result.safety_summary.eligible_count == len(candidates)
        assert result.safety_summary.catalog_count == len(decisions)

    def test_knee_injury_excludes_plyometrics_with_evidence(self, services: Services):
        result = tools.evaluate_workout_request(services, MEMBER_ID, INJURY_PROMPT)
        by_name = {e.name: e for e in result.excluded}

        jump = by_name.get("Static Jump")
        assert jump is not None, "plyometric must be excluded for a knee injury"
        assert "injury_contraindicated_pattern" in jump.rule_ids
        assert jump.evidence, "an exclusion must carry its graph traversal"

    def test_excluded_never_appears_as_eligible(self, services: Services):
        result = tools.evaluate_workout_request(services, MEMBER_ID, INJURY_PROMPT)
        excluded = {e.exercise_id for e in result.excluded}
        offered = {c.exercise_id for c in result.eligible_candidates}
        assert not (excluded & offered)

    def test_equipment_restriction_is_honoured(self, services: Services):
        result = tools.evaluate_workout_request(
            services,
            MEMBER_ID,
            "Full-body workout. She has no barbell, only dumbbells and a kettlebell.",
        )
        names = {e.name for e in result.excluded}
        assert "Barbell Decline Bench Press" in names

    def test_missing_member_raises(self, services: Services, monkeypatch):
        monkeypatch.setattr(
            services.repository, "get_member_context", lambda _member_id: None
        )
        with pytest.raises(tools.MemberNotFoundError):
            tools.evaluate_workout_request(services, "nope", INJURY_PROMPT)


# --- tool 3 ------------------------------------------------------------------


class TestGetMemberMetricTrend:
    def test_adherence_trend_is_real_data(self, services: Services, member):
        result = tools.get_member_metric_trend(services, MEMBER_ID, "adherence")
        recorded = sorted(
            member.adherence.weekly_completion_pct, key=lambda o: o.week_of
        )

        assert result.count == len(recorded)
        assert [o.label for o in result.observations] == [o.week_of for o in recorded]
        assert [o.value for o in result.observations] == [float(o.pct) for o in recorded]
        assert result.unit == "%"

    def test_arithmetic_is_deterministic_and_correct(self, services: Services):
        result = tools.get_member_metric_trend(services, MEMBER_ID, "adherence")
        values = [o.value for o in result.observations]

        assert result.first_value == values[0]
        assert result.latest_value == values[-1]
        assert result.absolute_delta == pytest.approx(values[-1] - values[0], abs=0.05)
        assert result.percent_delta == pytest.approx(
            (values[-1] - values[0]) / abs(values[0]) * 100, abs=0.05
        )
        assert result.computed_by == "deterministic_python"

    def test_sleep_trend_supported(self, services: Services):
        result = tools.get_member_metric_trend(services, MEMBER_ID, "sleep")
        assert result.count > 0
        assert result.unit == "hours"
        assert result.direction in {
            "improving",
            "declining",
            "stable",
            "insufficient_data",
        }

    def test_unsupported_metric_is_a_clean_error(self, services: Services):
        with pytest.raises(tools.UnsupportedMetricError) as exc:
            tools.get_member_metric_trend(services, MEMBER_ID, "vo2max")
        assert "Supported:" in str(exc.value)

    def test_fewer_than_two_observations_is_insufficient_data(
        self, services: Services
    ):
        result = tools.get_member_metric_trend(
            services, MEMBER_ID, "adherence", window=1
        )
        assert result.count == 1
        assert result.direction == "insufficient_data"
        assert result.absolute_delta is None

    def test_never_fabricates_observations(self, services: Services, monkeypatch):
        """An empty metric series must stay empty, not become a zero point."""
        monkeypatch.setattr(
            "app.copilot.analytics.weight_trend",
            lambda _m: __import__(
                "app.copilot.analytics", fromlist=["TrendResult"]
            ).TrendResult(),
        )
        result = tools.get_member_metric_trend(services, MEMBER_ID, "weight")
        assert result.observations == []
        assert result.direction == "insufficient_data"


# --- tool 4 ------------------------------------------------------------------


def _exercise_id(repository, name: str) -> str:
    for exercise in repository.list_exercises():
        if exercise.name == name:
            return exercise.id
    raise AssertionError(f"not in catalog: {name}")


class TestEvaluateExerciseSafety:
    def test_excluded_exercise_reports_injury_rule(self, services: Services):
        eid = _exercise_id(services.repository, "Static Jump")
        result = tools.evaluate_exercise_safety(services, MEMBER_ID, eid)

        assert result.status == "excluded"
        assert result.is_excluded is True
        assert "injury_contraindicated_pattern" in result.rule_ids
        assert result.injury_evidence, "the knee injury must be cited"
        assert result.graph_evidence
        assert result.authoritative is True

    def test_allowed_exercise_is_reported_as_allowed(self, services: Services):
        allowed = None
        for exercise in services.repository.list_exercises():
            verdict = tools.evaluate_exercise_safety(services, MEMBER_ID, exercise.id)
            if verdict.status == "allowed":
                allowed = verdict
                break
        assert allowed is not None, "some exercise must be allowed"
        assert allowed.is_excluded is False
        assert not allowed.missing_equipment

    def test_equipment_restriction_excludes_and_explains(self, services: Services):
        eid = _exercise_id(services.repository, "Barbell Decline Bench Press")
        result = tools.evaluate_exercise_safety(services, MEMBER_ID, eid)
        assert result.status == "excluded"
        assert "equipment_unavailable" in result.rule_ids
        assert result.missing_equipment

    def test_parity_with_direct_safety_engine(self, services: Services, member):
        """The contract: MCP result == direct SafetyEngine result."""
        from app.agents.intent import parse_intent as _parse

        intent, resolved = _parse("", 45, services.resolver)
        context = services.engine.build_context(member, intent, resolved)

        for exercise in services.repository.list_exercises():
            direct = services.engine.evaluate(exercise, context)
            viamcp = tools.evaluate_exercise_safety(services, MEMBER_ID, exercise.id)
            assert viamcp.status == direct.status, exercise.name
            assert viamcp.rule_ids == [r.rule_id for r in direct.reasons], exercise.name
            assert viamcp.score_adjustment == direct.score_adjustment, exercise.name

    def test_downranked_status_is_representable(self, services: Services):
        statuses = {
            tools.evaluate_exercise_safety(services, MEMBER_ID, e.id).status
            for e in services.repository.list_exercises()
        }
        assert statuses <= {"allowed", "downranked", "excluded"}

    def test_unknown_exercise_raises(self, services: Services):
        with pytest.raises(tools.ExerciseNotFoundError):
            tools.evaluate_exercise_safety(services, MEMBER_ID, "ex_nope")


# --- tool 5 ------------------------------------------------------------------


class TestGetExerciseProvenance:
    def test_serialises_real_graph_paths(self, services: Services):
        eid = _exercise_id(services.repository, "Static Jump")
        result = tools.get_exercise_provenance(services, MEMBER_ID, eid)

        assert result.has_graph_path is True
        path = result.graph_paths[0]
        assert path.nodes and path.relationships
        assert len(path.relationships) == len(path.nodes) - 1
        assert len(path.directions) == len(path.relationships)
        assert path.rendered

    def test_decision_matches_the_safety_engine(self, services: Services):
        for name in ["Static Jump", "Barbell Decline Bench Press"]:
            eid = _exercise_id(services.repository, name)
            safety = tools.evaluate_exercise_safety(services, MEMBER_ID, eid)
            provenance = tools.get_exercise_provenance(services, MEMBER_ID, eid)
            assert provenance.status == safety.status
            assert provenance.rule_ids == safety.rule_ids

    def test_part_of_anatomy_evidence_is_present(self, services: Services):
        eid = _exercise_id(services.repository, "Static Jump")
        result = tools.get_exercise_provenance(services, MEMBER_ID, eid)
        assert result.anatomy_evidence
        assert any("PART_OF" in line for line in result.anatomy_evidence)

    def test_no_path_is_fabricated_for_set_operations(self, services: Services):
        """Equipment absence is a set difference, so it must not grow an edge."""
        eid = _exercise_id(services.repository, "Barbell Decline Bench Press")
        result = tools.get_exercise_provenance(services, MEMBER_ID, eid)

        assert "equipment_unavailable" in result.rule_ids
        equipment_paths = [
            p for p in result.graph_paths if any("REQUIRES" in r for r in p.relationships)
        ]
        # A REQUIRES edge is real; what must never appear is an invented
        # "member does not have" relationship.
        for path in result.graph_paths:
            for relationship in path.relationships:
                assert "NOT_" not in relationship
                assert "MISSING" not in relationship.upper()
        assert result.equipment_evidence
        assert equipment_paths or result.evidence_note

    def test_states_when_no_traversal_exists(self, services: Services):
        allowed = next(
            e
            for e in services.repository.list_exercises()
            if tools.evaluate_exercise_safety(services, MEMBER_ID, e.id).status
            == "allowed"
        )
        result = tools.get_exercise_provenance(services, MEMBER_ID, allowed.id)
        if not result.has_graph_path:
            assert result.evidence_note, "absence of a path must be stated, not implied"


# --- tool 6 ------------------------------------------------------------------


class TestGetSafeExerciseCandidates:
    def test_excluded_never_appears_as_eligible(self, services: Services):
        result = tools.get_safe_exercise_candidates(services, MEMBER_ID, limit=100)
        eligible = {c.exercise_id for c in result.eligible_candidates}

        for exercise_id in eligible:
            verdict = tools.evaluate_exercise_safety(services, MEMBER_ID, exercise_id)
            assert not verdict.is_excluded, exercise_id

    def test_injury_filtering_applies(self, services: Services):
        result = tools.get_safe_exercise_candidates(
            services, MEMBER_ID, injury_mentions=["left knee"], limit=100
        )
        names = {c.name for c in result.eligible_candidates}
        assert "Static Jump" not in names
        assert result.excluded_count > 0

    def test_restrictive_equipment_filtering(self, services: Services):
        result = tools.get_safe_exercise_candidates(
            services, MEMBER_ID, equipment=["dumbbells", "kettlebell"], limit=100
        )
        assert result.applied_constraints.equipment_is_restrictive is True
        names = {c.name for c in result.eligible_candidates}
        assert "Barbell Decline Bench Press" not in names

    def test_explicit_exclusions_are_honoured(self, services: Services):
        result = tools.get_safe_exercise_candidates(
            services, MEMBER_ID, exclusions=["deadlifts"], limit=100
        )
        names = {c.name for c in result.eligible_candidates}
        assert "One-Kettlebell Hamstring Walkout" not in names

    def test_parity_with_the_existing_pipeline(self, services: Services, member):
        """Same member, no constraints: identical eligible set to the pipeline."""
        from app.agents.intent import parse_intent as _parse

        intent, resolved = _parse("", 45, services.resolver)
        context = services.engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in services.engine.evaluate_all(context)}
        expected = rank_candidates(
            services.repository.list_exercises(),
            decisions,
            member,
            intent,
            resolved,
            services.ontology,
        )

        result = tools.get_safe_exercise_candidates(services, MEMBER_ID, limit=1000)
        assert result.catalog_count == len(decisions)
        assert (
            result.eligible_count + result.downranked_count == len(expected)
        ), "eligible + downranked must account for every ranked candidate"

    def test_limit_is_applied_after_filtering_and_ranking(self, services: Services):
        full = tools.get_safe_exercise_candidates(services, MEMBER_ID, limit=1000)
        capped = tools.get_safe_exercise_candidates(services, MEMBER_ID, limit=3)

        # The count reflects the whole safe set; only the returned list is cut.
        assert capped.eligible_count == full.eligible_count
        assert capped.returned_count == 3
        assert len(capped.eligible_candidates) == 3
        # And it keeps the top-ranked ones, i.e. ranking happened first.
        assert [c.exercise_id for c in capped.eligible_candidates] == [
            c.exercise_id for c in full.eligible_candidates[:3]
        ]


# --- the MCP surface itself --------------------------------------------------


class TestMcpProtocolSurface:
    async def test_tools_are_advertised_with_schemas(self, mcp_client):
        async with mcp_client as client:
            listed = (await client.list_tools()).tools
            names = {t.name for t in listed}

        assert names == {
            "get_member_context",
            "resolve_coach_concepts",
            "get_member_metric_trend",
            "evaluate_exercise_safety",
            "get_exercise_provenance",
            "get_safe_exercise_candidates",
            "evaluate_workout_request",
        }, "all seven tools must be advertised"
        for tool in listed:
            assert tool.description
            assert tool.input_schema["type"] == "object"
            assert tool.output_schema, "structured output is the contract"

    async def test_round_trip_returns_structured_content(self, mcp_client):
        async with mcp_client as client:
            result = await client.call_tool(
                "get_member_context", {"member_id": MEMBER_ID}
            )

        assert result.is_error is False
        assert result.structured_content["member_id"] == MEMBER_ID

    async def test_safety_evaluation_over_the_protocol(self, mcp_client):
        async with mcp_client as client:
            result = await client.call_tool(
                "evaluate_workout_request",
                {"member_id": MEMBER_ID, "prompt": INJURY_PROMPT},
            )

        payload = result.structured_content
        assert result.is_error is False
        assert payload["composed_workout"] is None
        assert payload["safety_summary"]["excluded_count"] > 0
        assert any(
            "injury_contraindicated_pattern" in item["rule_ids"]
            for item in payload["excluded"]
        )

    async def test_missing_argument_is_a_protocol_error(self, mcp_client):
        async with mcp_client as client:
            result = await client.call_tool("get_member_context", {})
        assert result.is_error is True

    def test_mounted_transport_serves_the_protocol(self, monkeypatch):
        """Regression: Starlette's Mount does not run a sub-app's lifespan.

        Without ``mcp_session_lifespan`` in the host lifespan the app still
        imports, starts, and serves REST traffic normally - then fails on the
        first MCP request with "Task group is not initialized". Only an actual
        HTTP round-trip catches it, so this test drives one.
        """
        from starlette.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.core.config import get_settings
        from app.main import create_app

        monkeypatch.setenv("MCP_ALLOWED_HOSTS", '["testserver"]')
        get_settings.cache_clear()
        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        try:
            with TestClient(create_app()) as client:
                response = client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                    headers=headers,
                )
                assert response.status_code == 200, response.text

                # REST must remain untouched by the mount.
                assert client.get("/api/health").status_code == 200
        finally:
            get_settings.cache_clear()
            mcp_server_module._asgi_app = None

    def test_unlisted_host_is_rejected(self, monkeypatch):
        """DNS-rebinding protection must stay on for a server exposing member data."""
        from starlette.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.core.config import get_settings
        from app.main import create_app

        monkeypatch.setenv("MCP_ALLOWED_HOSTS", '["example.invalid"]')
        get_settings.cache_clear()
        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)
        try:
            with TestClient(create_app()) as client:
                response = client.post(
                    "/mcp/",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
                assert response.status_code == 421
        finally:
            get_settings.cache_clear()
            mcp_server_module._asgi_app = None

    async def test_tool_exceptions_surface_as_protocol_errors(
        self, services: Services, monkeypatch
    ):
        """A raised tool error must become is_error, not a crashed session."""
        monkeypatch.setattr(
            services.repository, "get_member_context", lambda _member_id: None
        )
        server = create_mcp_server(services_provider=lambda: services)
        async with Client(InMemoryTransport(server)) as client:
            result = await client.call_tool(
                "get_member_context", {"member_id": "mbr_nope"}
            )
        assert result.is_error is True
