"""Copilot tests.

The risk with a retrieval assistant is not that it crashes - it is that it
answers fluently and wrongly. These tests pin the three properties that protect
against that:

1. answers are computed from the member graph, not improvised;
2. missing data produces an admission, never an invention;
3. chart payloads match the underlying observations exactly, because a chart is
   an assertion about data just as much as a sentence is.
"""

from __future__ import annotations

import pytest

from app.copilot import analytics
from app.copilot.service import CopilotService, classify
from app.llm.stub import StubLLMClient


@pytest.fixture
def copilot() -> CopilotService:
    return CopilotService(StubLLMClient())


class TestIntentClassification:
    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("Show me the brief", "SHOW_BRIEF"),
            ("How's adherence trending?", "ADHERENCE_TREND"),
            ("Sleep this week", "SLEEP_WEEK"),
            ("What changed since last week?", "WHAT_CHANGED"),
            ("Is there any churn risk?", "CHURN_RISK"),
            ("Show message pattern", "MESSAGE_PATTERN"),
            ("What were her last workouts?", "WORKOUT_HISTORY"),
            ("What did her blood panel show?", "LABS"),
            ("Tell me about this member", "GENERAL_MEMBER_QA"),
        ],
    )
    def test_quick_prompts_route_correctly(self, message, expected):
        assert classify(message) == expected


class TestAnswersUseRealMemberData:
    async def test_adherence_answer_matches_the_graph(self, copilot, member):
        response = await copilot.answer(member, "How's adherence trending?")

        recorded = [o.pct for o in member.adherence.weekly_completion_pct]
        assert response.evidence["values"] == [float(p) for p in recorded]
        assert response.evidence["latest_pct"] == float(recorded[-1])
        assert response.evidence["direction"] == "declining"
        assert response.citations

    async def test_sleep_answer_matches_the_graph(self, copilot, member):
        response = await copilot.answer(member, "Sleep this week")
        nights = member.biomarkers.sleep_hours_last_7_days

        assert response.evidence["values"] == [float(n) for n in nights]
        assert response.evidence["average_hours"] == pytest.approx(
            sum(nights) / len(nights), abs=0.01
        )
        assert response.evidence["nights_below_7"] == sum(1 for n in nights if n < 7)

    async def test_brief_reflects_the_recorded_tasks(self, copilot, member):
        response = await copilot.answer(member, "Show me the brief")
        tasks = [t["text"] for t in response.evidence["morning_tasks"]]

        assert tasks == [t.text for t in member.coach_brief.morning_tasks]
        assert response.evidence["generated_for"] == member.coach_brief.generated_for

    async def test_churn_uses_the_recorded_signal_not_a_guess(self, copilot, member):
        response = await copilot.answer(member, "Is there any churn risk?")

        assert response.evidence["level"] == member.coach_brief.churn_risk.level
        assert response.evidence["reasons"] == member.coach_brief.churn_risk.reasons
        assert response.evidence["source"] == "coach_brief"

    async def test_answer_mentions_the_member_by_name(self, copilot, member):
        response = await copilot.answer(member, "How's adherence trending?")
        assert member.profile.name.split()[0] in response.answer

    async def test_message_pattern_counts_are_exact(self, copilot, member):
        response = await copilot.answer(member, "Show message pattern")
        assert response.evidence["total_messages"] == len(member.chat_history)

    async def test_attachments_are_surfaced_without_inventing_contents(
        self, copilot, member
    ):
        response = await copilot.answer(member, "Show me the chat history")
        attachments = response.evidence["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["caption"] == "Home setup photo (synthetic placeholder)"


class TestMissingDataIsNotInvented:
    async def test_absent_labs_produce_an_admission(self, copilot, member):
        stripped = member.model_copy(deep=True)
        stripped.labs.blood_panel = None
        stripped.labs.dexa_scan = None

        response = await copilot.answer(stripped, "What did her blood panel show?")

        assert "No lab results" in response.answer
        assert response.chart is None
        assert response.generator == "deterministic"

    async def test_absent_adherence_produces_an_admission(self, copilot, member):
        stripped = member.model_copy(deep=True)
        stripped.adherence.weekly_completion_pct = []

        response = await copilot.answer(stripped, "How's adherence trending?")

        assert "No adherence data" in response.answer
        assert response.chart is None

    async def test_absent_sleep_data_is_not_fabricated(self, copilot, member):
        stripped = member.model_copy(deep=True)
        stripped.biomarkers.sleep_hours_last_7_days = []

        response = await copilot.answer(stripped, "Sleep this week")
        assert "No sleep data" in response.answer

    async def test_full_member_json_is_not_dumped_into_the_prompt(
        self, copilot, member
    ):
        """Retrieval must be a slice, not the whole record."""
        response = await copilot.answer(member, "How's adherence trending?")

        keys = set(response.evidence)
        assert "labs" not in keys
        assert "chat_history" not in keys
        assert "workout_history" not in keys


class TestChartsMatchTheData:
    async def test_adherence_chart_values_equal_the_observations(
        self, copilot, member
    ):
        response = await copilot.answer(member, "Plot adherence trend")
        chart = response.chart

        assert chart is not None
        assert chart.type == "line"
        assert chart.series[0].values == [
            float(o.pct) for o in member.adherence.weekly_completion_pct
        ]
        assert len(chart.x) == len(chart.series[0].values)

    async def test_sleep_chart_values_equal_the_observations(self, copilot, member):
        response = await copilot.answer(member, "Sleep this week")
        chart = response.chart

        assert chart is not None
        assert chart.type == "bar"
        assert chart.series[0].values == [
            float(n) for n in member.biomarkers.sleep_hours_last_7_days
        ]

    async def test_chart_axis_labels_are_present_for_rendering(self, copilot, member):
        response = await copilot.answer(member, "How's adherence trending?")
        assert response.chart.y_domain == [0, 100]
        assert all(label.startswith("Week of") for label in response.chart.x)


class TestAnalyticsAreDeterministic:
    def test_adherence_direction_is_computed_not_copied(self, member):
        trend = analytics.adherence_trend(member)
        assert trend.direction == "declining"
        assert trend.delta == pytest.approx(-50.0)

    def test_session_stats_match_history(self, member):
        stats = analytics.session_stats(member)
        completed = [s for s in member.workout_history if s.completed]

        assert stats.completed == len(completed)
        assert stats.total_minutes == sum(s.duration_min for s in completed)
        assert stats.missed_dates == [
            s.date for s in member.workout_history if s.planned and not s.completed
        ]

    def test_what_changed_compares_the_last_two_weeks(self, member):
        change = analytics.what_changed(member)
        assert change.weeks_compared == 2
        assert change.adherence_delta == pytest.approx(-25.0)

    def test_flat_trend_is_not_reported_as_a_change(self, member):
        flat = member.model_copy(deep=True)
        for observation in flat.adherence.weekly_completion_pct:
            observation.pct = 80
        assert analytics.adherence_trend(flat).direction == "flat"
