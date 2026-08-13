"""Deterministic member analytics.

Every number the copilot states is computed here, in Python, from the member
graph - never by the LLM. Trends, deltas and averages are arithmetic, and
arithmetic done by a language model is both unnecessary and unverifiable.

The LLM's only job downstream is to phrase these numbers in a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from app.domain.member import MemberContext


@dataclass
class TrendResult:
    values: list[float] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    direction: str = "insufficient_data"
    delta: float | None = None
    latest: float | None = None
    average: float | None = None
    first: float | None = None

    @property
    def has_data(self) -> bool:
        return bool(self.values)


def adherence_trend(member: MemberContext) -> TrendResult:
    observations = member.adherence.weekly_completion_pct
    if not observations:
        return TrendResult()

    ordered = sorted(observations, key=lambda o: o.week_of)
    values = [float(o.pct) for o in ordered]
    labels = [o.week_of for o in ordered]

    result = TrendResult(
        values=values,
        labels=labels,
        latest=values[-1],
        first=values[0],
        average=round(mean(values), 1),
    )
    if len(values) >= 2:
        result.delta = round(values[-1] - values[0], 1)
        result.direction = _direction(result.delta, flat_band=5.0)
    else:
        result.direction = "insufficient_data"
    return result


def sleep_trend(member: MemberContext) -> TrendResult:
    nights = member.biomarkers.sleep_hours_last_7_days
    if not nights:
        return TrendResult()

    values = [float(n) for n in nights]
    labels = [f"Night {i + 1}" for i in range(len(values))]
    result = TrendResult(
        values=values,
        labels=labels,
        latest=values[-1],
        first=values[0],
        average=round(mean(values), 2),
    )
    if len(values) >= 4:
        half = len(values) // 2
        result.delta = round(mean(values[half:]) - mean(values[:half]), 2)
        result.direction = _direction(result.delta, flat_band=0.3)
    return result


def weight_trend(member: MemberContext) -> TrendResult:
    points = member.biomarkers.weight_trend_kg
    if not points:
        return TrendResult()
    ordered = sorted(points, key=lambda p: p.date)
    values = [float(p.kg) for p in ordered]
    result = TrendResult(
        values=values,
        labels=[p.date for p in ordered],
        latest=values[-1],
        first=values[0],
        average=round(mean(values), 2),
    )
    if len(values) >= 2:
        result.delta = round(values[-1] - values[0], 2)
        result.direction = _direction(result.delta, flat_band=0.3)
    return result


def _direction(delta: float, flat_band: float) -> str:
    if abs(delta) <= flat_band:
        return "flat"
    return "improving" if delta > 0 else "declining"


@dataclass
class SessionStats:
    completed: int = 0
    planned: int = 0
    completion_rate: float | None = None
    total_minutes: int = 0
    average_rpe: float | None = None
    last_completed_title: str | None = None
    last_completed_date: str | None = None
    missed_dates: list[str] = field(default_factory=list)


def session_stats(member: MemberContext) -> SessionStats:
    history = member.workout_history
    if not history:
        return SessionStats()

    completed = [s for s in history if s.completed]
    rpes = [float(s.rpe) for s in completed if s.rpe is not None]
    ordered_completed = sorted(completed, key=lambda s: s.date, reverse=True)

    return SessionStats(
        completed=len(completed),
        planned=len([s for s in history if s.planned]),
        completion_rate=(
            round(100 * len(completed) / len(history), 1) if history else None
        ),
        total_minutes=sum(s.duration_min for s in completed),
        average_rpe=round(mean(rpes), 1) if rpes else None,
        last_completed_title=ordered_completed[0].title if ordered_completed else None,
        last_completed_date=ordered_completed[0].date if ordered_completed else None,
        missed_dates=[s.date for s in history if s.planned and not s.completed],
    )


@dataclass
class ChurnAssessment:
    level: str
    reasons: list[str] = field(default_factory=list)
    supporting_metrics: dict[str, float | str | None] = field(default_factory=dict)
    source: str = "coach_brief"


def churn_assessment(member: MemberContext) -> ChurnAssessment:
    """Report the recorded churn signal, corroborated by computed metrics.

    We do not invent a risk score. The member graph carries an explicit churn
    signal; we surface it and attach the arithmetic that supports or qualifies
    it, so a coach can see the reasoning rather than a bare label.
    """
    brief = member.coach_brief
    adherence = adherence_trend(member)
    sessions = session_stats(member)

    if brief.churn_risk:
        level = brief.churn_risk.level
        reasons = list(brief.churn_risk.reasons)
        source = "coach_brief"
    else:
        level = "unknown"
        reasons = []
        source = "computed"

    return ChurnAssessment(
        level=level,
        reasons=reasons,
        source=source,
        supporting_metrics={
            "adherence_latest_pct": adherence.latest,
            "adherence_delta_pct": adherence.delta,
            "adherence_direction": adherence.direction,
            "sessions_completed": sessions.completed,
            "sessions_missed": len(sessions.missed_dates),
            "avg_sleep_hours": sleep_trend(member).average,
        },
    )


@dataclass
class WeekOverWeekChange:
    changes: list[str] = field(default_factory=list)
    adherence_delta: float | None = None
    weeks_compared: int = 0


def what_changed(member: MemberContext) -> WeekOverWeekChange:
    """Compare the two most recent adherence weeks plus session activity."""
    result = WeekOverWeekChange()
    observations = sorted(
        member.adherence.weekly_completion_pct, key=lambda o: o.week_of
    )
    if len(observations) >= 2:
        latest, previous = observations[-1], observations[-2]
        result.adherence_delta = round(float(latest.pct) - float(previous.pct), 1)
        result.weeks_compared = 2
        verb = "fell" if result.adherence_delta < 0 else "rose"
        if result.adherence_delta == 0:
            result.changes.append(
                f"Adherence held steady at {latest.pct}% (week of {latest.week_of})."
            )
        else:
            result.changes.append(
                f"Adherence {verb} from {previous.pct}% to {latest.pct}% "
                f"(week of {latest.week_of})."
            )

    sessions = session_stats(member)
    if sessions.last_completed_title:
        result.changes.append(
            f"Most recent completed session: {sessions.last_completed_title} "
            f"on {sessions.last_completed_date}."
        )
    if sessions.missed_dates:
        result.changes.append(
            f"Missed {len(sessions.missed_dates)} planned session(s): "
            f"{', '.join(sessions.missed_dates)}."
        )

    sleep = sleep_trend(member)
    if sleep.has_data and sleep.average is not None:
        result.changes.append(
            f"Sleep averaged {sleep.average}h over the last {len(sleep.values)} nights "
            f"({sleep.direction})."
        )
    return result
