"""Evaluation-harness and tracing tests.

Two properties, and the second is the one that would be expensive to get wrong:

1. **Metrics are honest.** Every ratio is a real numerator over a real
   denominator, invariants are computed from executed cases, and a run with a
   single unsafe escape fails loudly rather than averaging it away.
2. **Tracing is observational.** Removing the trace layer must leave every
   safety decision byte-identical, and no trace may carry a member payload, a
   prompt body or a coach's question.

The dataset here is synthetic. The privacy tests exist because the layer should
be designed as though it were not.
"""

from __future__ import annotations

import json

import pytest

from app.api.deps import Services
from app.core.config import get_settings
from app.domain.evaluation import EvaluationRun, Invariant, Metric
from app.domain.trace import NODE_ZONE, SAFE_CANDIDATE_BOUNDARY, RequestTrace
from app.evaluation.artifacts import EvaluationArtifactStore
from app.evaluation.cases import ALL_CASES, cases_by_category
from app.evaluation.runner import EvaluationRunner
from app.llm.stub import StubLLMClient
from app.member.trajectory import MemberTrajectoryService
from app.observability.collector import (
    InstrumentedGraphRepository,
    build_workflow_trace,
    graph_call_scope,
)
from app.observability.store import TraceStore

from .conftest import MEMBER_ID

#: A cheap, representative slice. The full corpus runs in scripts/run_evals.py;
#: re-running all 71 cases inside the unit suite would triple its duration for
#: no extra signal about the harness itself.
SMOKE_CASE_IDS = [
    "res-exact-kettlebell",
    "res-unresolved-nonsense",
    "safe-knee-plyometric",
    "safe-counts-injury",
    "equip-no-barbell",
    "excl-deadlift-family",
    "long-progression-hold",
    "val-excluded-exercise",
    "val-hallucinated-id",
    "mcp-safety-parity",
]


@pytest.fixture
def services(repository, ontology, resolver, engine) -> Services:
    trajectory = MemberTrajectoryService(ontology)
    from app.agents.workout_graph import WorkoutWorkflow
    from app.copilot.service import CopilotService

    return Services(
        settings=get_settings(),
        ontology=ontology,
        repository=repository,
        resolver=resolver,
        engine=engine,
        llm=StubLLMClient(),
        workflow=WorkoutWorkflow(
            repository, ontology, resolver, engine, StubLLMClient(), trajectory
        ),
        copilot=CopilotService(StubLLMClient(), trajectory_service=trajectory),
        backend="memory",
        trajectory=trajectory,
    )


@pytest.fixture
def smoke_cases():
    wanted = set(SMOKE_CASE_IDS)
    return [case for case in ALL_CASES if case.id in wanted]


# --- the corpus itself -------------------------------------------------------


class TestCorpus:
    def test_every_case_has_a_handler(self, services):
        """A case whose kind has no runner would silently never be measured."""
        runner = EvaluationRunner(services)
        missing = [c.id for c in ALL_CASES if not hasattr(runner, f"_case_{c.kind}")]
        assert missing == []

    def test_case_ids_are_unique(self):
        ids = [case.id for case in ALL_CASES]
        assert len(ids) == len(set(ids))

    def test_every_category_is_covered(self):
        grouped = cases_by_category()
        for category in (
            "concept_resolution",
            "safety",
            "equipment",
            "exclusion",
            "longitudinal",
            "adjustment",
            "validation",
            "copilot_mcp",
        ):
            assert grouped.get(category), f"no cases for {category}"

    def test_the_corpus_is_substantial(self):
        assert len(ALL_CASES) >= 30


# --- runner and metrics ------------------------------------------------------


class TestRunner:
    async def test_the_runner_executes_and_reports(self, services, smoke_cases):
        run = await EvaluationRunner(services).run(smoke_cases)

        assert run.total_cases == len(smoke_cases)
        assert run.passed_cases + run.failed_cases == run.total_cases
        assert run.results and all(r.latency_ms >= 0 for r in run.results)

    async def test_the_smoke_slice_passes(self, services, smoke_cases):
        run = await EvaluationRunner(services).run(smoke_cases)
        failures = [(r.case_id, r.actual) for r in run.results if not r.passed]
        assert failures == []
        assert run.status == "pass"

    async def test_metrics_carry_a_real_numerator_and_denominator(
        self, services, smoke_cases
    ):
        run = await EvaluationRunner(services).run(smoke_cases)

        for metric in run.metrics:
            assert metric.numerator <= metric.denominator
            assert metric.numerator >= 0
            if metric.denominator == 0:
                # "nothing measured" must not render as 0% success.
                assert metric.value is None
            else:
                assert metric.value == pytest.approx(
                    metric.numerator / metric.denominator, abs=1e-4
                )

    async def test_category_denominators_match_the_executed_cases(
        self, services, smoke_cases
    ):
        run = await EvaluationRunner(services).run(smoke_cases)
        safety = run.metric("hard_safety_satisfaction")
        expected = sum(1 for c in smoke_cases if c.category == "safety")

        assert safety is not None
        assert safety.denominator == expected

    async def test_unsafe_escape_metric_is_zero_and_flagged_lower_is_better(
        self, services, smoke_cases
    ):
        run = await EvaluationRunner(services).run(smoke_cases)
        metric = run.metric("unsafe_escape_rate")

        assert metric is not None
        assert metric.higher_is_better is False
        assert metric.numerator == 0
        assert run.unsafe_escapes == 0

    async def test_a_failing_validation_case_is_counted_as_an_unsafe_escape(
        self, services
    ):
        """The metric must react, not merely exist."""
        from app.evaluation.cases import EvalCase

        broken = EvalCase(
            id="val-synthetic-failure",
            category="validation",
            name="Synthetic failure",
            kind="adversarial",
            input_summary="deliberately broken",
            expectation="fails",
            params={"mode": "not-a-real-mode", "prompt": "lower body"},
        )
        run = await EvaluationRunner(services).run([broken])

        assert run.unsafe_escapes == 1
        assert run.status == "fail"

    async def test_the_run_is_deterministic(self, services, smoke_cases):
        """Same corpus, same code, same outcomes - or the suite means nothing."""
        first = await EvaluationRunner(services).run(smoke_cases)
        second = await EvaluationRunner(services).run(smoke_cases)

        assert [(r.case_id, r.passed, r.actual) for r in first.results] == [
            (r.case_id, r.passed, r.actual) for r in second.results
        ]

    async def test_provenance_coverage_is_measured_not_asserted(self, services):
        coverage_case = next(c for c in ALL_CASES if c.id == "safe-provenance-coverage")
        run = await EvaluationRunner(services).run([coverage_case])
        metric = run.metric("provenance_coverage")

        assert metric is not None
        assert metric.denominator == 1
        assert metric.numerator == 1

    async def test_safety_cases_capture_graph_evidence(self, services):
        case = next(c for c in ALL_CASES if c.id == "safe-knee-plyometric")
        run = await EvaluationRunner(services).run([case])
        result = run.results[0]

        assert result.evidence
        evidence = result.evidence[0]
        assert evidence.rule_ids
        # Reuses the coach UI's traversal model rather than a second shape.
        assert evidence.traversals
        assert {t.path_kind for t in evidence.traversals} <= {
            "member_context",
            "anatomy_hierarchy",
            "exercise_structure",
            "set_operation",
        }

    async def test_latency_summary_is_populated(self, services, smoke_cases):
        run = await EvaluationRunner(services).run(smoke_cases)
        assert run.latency.p50_ms is not None
        assert run.latency.p95_ms is not None
        assert run.latency.max_ms >= run.latency.p50_ms


class TestInvariants:
    async def test_invariants_are_derived_from_executed_cases(
        self, services, smoke_cases
    ):
        run = await EvaluationRunner(services).run(smoke_cases)

        for invariant in run.invariants:
            if invariant.holds:
                assert invariant.proven_by, f"{invariant.key} holds with no evidence"
                assert not invariant.failed_by

    def test_an_invariant_with_no_evidence_does_not_hold(self):
        """Absence of a failure is not a demonstration."""
        invariant = Invariant(key="k", statement="s", holds=False, detail="no case")
        assert invariant.holds is False
        assert invariant.evidence_count == 0

    async def test_a_failing_case_breaks_its_invariant(self, services):
        """Green ticks must be falsifiable."""
        from app.evaluation.cases import EvalCase

        broken = EvalCase(
            id="safe-knee-plyometric",  # id an invariant depends on
            category="safety",
            name="Deliberately broken",
            kind="safety",
            input_summary="broken",
            expectation="fails",
            params={"prompt": "lower body", "excluded": ["Walking Toe Touches"]},
        )
        run = await EvaluationRunner(services).run([broken])
        invariant = next(i for i in run.invariants if i.key == "graph_decides_safety")

        assert invariant.holds is False
        assert "safe-knee-plyometric" in invariant.failed_by


# --- artifacts ---------------------------------------------------------------


class TestArtifacts:
    def _run(self) -> EvaluationRun:
        return EvaluationRun(
            run_id="eval-20260101T000000Z-abc123",
            started_at="2026-01-01T00:00:00+00:00",
            graph_backend="memory",
            llm_provider="stub",
            total_cases=1,
            passed_cases=1,
            metrics=[Metric(key="k", label="K", numerator=1, denominator=1)],
        )

    def test_saving_writes_the_run_and_refreshes_latest(self, tmp_path):
        store = EvaluationArtifactStore(tmp_path)
        path = store.save(self._run())

        assert path.exists()
        assert (tmp_path / "latest.json").exists()
        assert store.latest().run_id == "eval-20260101T000000Z-abc123"

    def test_a_saved_run_round_trips(self, tmp_path):
        store = EvaluationArtifactStore(tmp_path)
        store.save(self._run())
        loaded = store.get("eval-20260101T000000Z-abc123")

        assert loaded is not None
        assert loaded.metrics[0].value == 1.0
        assert loaded.status == "pass"

    def test_history_lists_runs_newest_first_and_excludes_latest(self, tmp_path):
        store = EvaluationArtifactStore(tmp_path)
        for suffix in ("a", "b"):
            run = self._run()
            run.run_id = f"eval-2026010{suffix and 1}T00000{suffix}Z-{suffix * 6}"
            store.save(run)

        history = store.history()
        assert history.count == 2
        assert all(r.run_id != "latest" for r in history.runs)

    def test_missing_artifacts_are_absent_not_invented(self, tmp_path):
        store = EvaluationArtifactStore(tmp_path)
        assert store.latest() is None
        assert store.get("eval-nope") is None
        assert store.history().count == 0

    def test_a_corrupt_artifact_is_skipped_not_fatal(self, tmp_path):
        store = EvaluationArtifactStore(tmp_path)
        store.save(self._run())
        (tmp_path / "eval-broken.json").write_text("{not json", encoding="utf-8")

        assert store.history().count == 1

    def test_a_malicious_run_id_cannot_escape_the_directory(self, tmp_path):
        store = EvaluationArtifactStore(tmp_path)
        with pytest.raises(ValueError):
            store.get("../../etc/passwd")


# --- tracing -----------------------------------------------------------------


class TestTraceStore:
    def test_traces_are_newest_first_and_bounded(self):
        store = TraceStore(capacity=3)
        for index in range(5):
            store.record(
                RequestTrace(request_id=f"r{index}", workflow="generate")
            )

        recent = store.recent()
        assert [t.request_id for t in recent] == ["r4", "r3", "r2"]
        assert store.capacity == 3

    def test_a_trace_can_be_fetched_by_id(self):
        store = TraceStore()
        store.record(RequestTrace(request_id="abc", workflow="copilot"))
        assert store.get("abc") is not None
        assert store.get("nope") is None


class TestWorkflowTrace:
    async def _state(self, repository, ontology, resolver, engine, prompt=None):
        from app.agents.workout_graph import WorkoutWorkflow
        from app.domain.workout import WorkoutRequest

        workflow = WorkoutWorkflow(
            repository, ontology, resolver, engine, StubLLMClient()
        )
        return await workflow.run(
            WorkoutRequest(
                member_id=MEMBER_ID,
                prompt=prompt
                or "Create a 45-minute lower-body workout. Her left knee is bothering her.",
                duration_minutes=45,
            )
        )

    async def test_every_workflow_node_appears_as_a_span(
        self, repository, ontology, resolver, engine
    ):
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1",
            workflow="generate",
            member_id=MEMBER_ID,
            state=state,
            total_duration_ms=42.0,
        )
        names = [span.name for span in trace.spans]

        for node in (
            "load_member",
            "parse_intent_and_resolve",
            "analyze_longitudinal_context",
            "evaluate_safety",
            "rank_candidates",
            "compose_workout_llm",
            "validate_workout",
            "build_provenance",
        ):
            assert node in names

    async def test_span_durations_are_non_negative(
        self, repository, ontology, resolver, engine
    ):
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        assert all(span.duration_ms >= 0 for span in trace.spans)
        assert trace.total_duration_ms >= 0

    async def test_the_total_is_not_double_counted_as_a_span(
        self, repository, ontology, resolver, engine
    ):
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        assert "total" not in {span.name for span in trace.spans}

    async def test_spans_are_zoned_and_the_boundary_is_locatable(
        self, repository, ontology, resolver, engine
    ):
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        zones = {span.name: span.zone for span in trace.spans}

        assert zones["evaluate_safety"] == "deterministic"
        assert zones["compose_workout_llm"] == "generative"
        assert SAFE_CANDIDATE_BOUNDARY in zones
        assert NODE_ZONE[SAFE_CANDIDATE_BOUNDARY] == "deterministic"

    async def test_safety_summary_matches_the_decisions(
        self, repository, ontology, resolver, engine
    ):
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        decisions = state["safety_decisions"]

        assert trace.safety is not None
        assert trace.safety.catalog_count == len(decisions)
        assert trace.safety.excluded_count == sum(
            1 for d in decisions.values() if d.is_excluded
        )
        assert trace.safety.rules_fired

    async def test_resolver_methods_are_counted_not_quoted(
        self, repository, ontology, resolver, engine
    ):
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        assert trace.resolution is not None
        assert sum(trace.resolution.method_counts.values()) == len(
            state["resolved_concepts"]
        )
        # Methods, not phrases: no coach wording may appear as a key.
        assert set(trace.resolution.method_counts) <= {
            "exact", "alias", "fuzzy", "embedding", "unresolved",
        }

    async def test_absent_token_usage_is_null_not_zero(
        self, repository, ontology, resolver, engine
    ):
        """The offline stub reports no usage; absent is the honest value."""
        state = await self._state(repository, ontology, resolver, engine)
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        assert trace.llm_input_tokens is None
        assert trace.llm_output_tokens is None
        assert trace.graph_query_count is None  # no counter installed here


class TestTracingIsObservational:
    """The property the whole layer is designed around."""

    def test_the_instrumented_repository_is_a_pass_through(
        self, repository, ontology, resolver, engine, member
    ):
        from app.agents.intent import parse_intent
        from app.safety.engine import SafetyEngine

        prompt = "Create a 45-minute lower-body workout. Her left knee is bothering her."
        intent, resolved = parse_intent(prompt, 45, resolver)

        plain = engine.build_context(member, intent, resolved)
        plain_decisions = {d.exercise_id: d.status for d in engine.evaluate_all(plain)}

        wrapped_engine = SafetyEngine(InstrumentedGraphRepository(repository), ontology)
        wrapped = wrapped_engine.build_context(member, intent, resolved)
        wrapped_decisions = {
            d.exercise_id: d.status for d in wrapped_engine.evaluate_all(wrapped)
        }

        assert plain_decisions == wrapped_decisions

    def test_graph_calls_are_counted_only_inside_a_scope(self, repository):
        instrumented = InstrumentedGraphRepository(repository)

        instrumented.list_exercises()  # outside a scope: not counted, no error
        with graph_call_scope() as scope:
            instrumented.list_exercises()
            instrumented.exercise_patterns("x")
        assert scope.count == 2
        assert set(scope.by_method) == {"list_exercises", "exercise_patterns"}

    def test_non_query_attributes_are_not_counted(self, repository):
        instrumented = InstrumentedGraphRepository(repository)
        with graph_call_scope() as scope:
            instrumented.stats()
            assert instrumented.backend_name == "memory"
        assert scope.count == 0


class TestTracePrivacy:
    """Nothing sensitive may reach a serialized trace.

    The current dataset is synthetic. These tests exist so the layer stays
    designed for data that would not be.
    """

    FORBIDDEN_KEYS = {
        "member_context", "chat_history", "labs", "blood_panel", "dexa_scan",
        "prompt", "base_prompt", "message", "question", "answer", "payload",
        "api_key", "authorization", "headers", "attachments", "notes",
    }

    async def test_a_workflow_trace_carries_no_sensitive_field(
        self, repository, ontology, resolver, engine
    ):
        from app.agents.workout_graph import WorkoutWorkflow
        from app.domain.workout import WorkoutRequest

        workflow = WorkoutWorkflow(
            repository, ontology, resolver, engine, StubLLMClient()
        )
        state = await workflow.run(
            WorkoutRequest(
                member_id=MEMBER_ID,
                prompt="Create a lower-body workout. Her left knee is bothering her.",
                duration_minutes=45,
            )
        )
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        payload = json.loads(trace.model_dump_json())

        assert _keys(payload).isdisjoint(self.FORBIDDEN_KEYS)

    async def test_the_coach_prompt_never_appears_in_a_trace(
        self, repository, ontology, resolver, engine
    ):
        from app.agents.workout_graph import WorkoutWorkflow
        from app.domain.workout import WorkoutRequest

        secret = "Her left knee is bothering her"
        workflow = WorkoutWorkflow(
            repository, ontology, resolver, engine, StubLLMClient()
        )
        state = await workflow.run(
            WorkoutRequest(
                member_id=MEMBER_ID,
                prompt=f"Create a 45-minute lower-body workout. {secret}.",
                duration_minutes=45,
            )
        )
        trace = build_workflow_trace(
            request_id="r1", workflow="generate", member_id=MEMBER_ID,
            state=state, total_duration_ms=42.0,
        )
        assert secret.lower() not in trace.model_dump_json().lower()

    def test_a_copilot_trace_records_the_intent_not_the_question(self):
        from app.copilot.service import Grounding
        from app.observability.collector import build_copilot_trace

        trace = build_copilot_trace(
            request_id="r2",
            member_id=MEMBER_ID,
            intent="ADHERENCE_TREND",
            total_duration_ms=18.0,
            grounding=Grounding(
                mode="mcp",
                tools_used=["get_member_metric_trend"],
                authoritative_safety=True,
            ),
            generator="stub",
        )
        payload = trace.model_dump_json()

        assert trace.mcp is not None
        assert trace.mcp.intent == "ADHERENCE_TREND"
        assert "how's adherence" not in payload.lower()
        assert _keys(json.loads(payload)).isdisjoint(self.FORBIDDEN_KEYS)

    def test_an_adjustment_trace_records_counts_not_the_instruction(self):
        from app.domain.trace import AdjustmentTraceSummary

        summary = AdjustmentTraceSummary(removed_count=1, added_count=1)
        payload = json.loads(summary.model_dump_json())

        assert set(payload) == {
            "removed_count", "added_count", "downranked_count", "retained_count",
            "newly_excluded_count", "duration_minutes", "baseline_rerun_ms",
        }


def _keys(payload) -> set[str]:
    """Every key appearing anywhere in a nested structure."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            found |= _keys(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _keys(item)
    return found


# --- HTTP surface ------------------------------------------------------------


class TestSystemEndpoints:
    async def test_traces_and_evaluations_are_served(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.main import create_app

        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)

        with TestClient(create_app()) as client:
            client.post(
                "/api/workouts/generate",
                json={
                    "member_id": MEMBER_ID,
                    "prompt": "Create a 45-minute lower-body workout.",
                    "duration_minutes": 45,
                },
            )
            listing = client.get("/api/system/traces")
            assert listing.status_code == 200
            body = listing.json()
            assert body["count"] >= 1

            request_id = body["traces"][0]["request_id"]
            detail = client.get(f"/api/system/traces/{request_id}")
            assert detail.status_code == 200
            assert detail.json()["request_id"] == request_id

            assert client.get("/api/system/traces/nope").status_code == 404
            assert client.get("/api/system/evaluations").status_code == 200
            assert client.get("/api/system/evaluations/latest").status_code == 200

    async def test_a_traced_request_reports_graph_queries(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.main import create_app

        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)

        with TestClient(create_app()) as client:
            client.post(
                "/api/workouts/generate",
                json={
                    "member_id": MEMBER_ID,
                    "prompt": "Create a 45-minute lower-body workout.",
                    "duration_minutes": 45,
                },
            )
            trace = client.get("/api/system/traces").json()["traces"][0]

        # The counter is installed in the composition root, so a real request
        # reports a number rather than the None a bare workflow would.
        assert trace["graph_query_count"] is not None
        assert trace["graph_query_count"] > 0
