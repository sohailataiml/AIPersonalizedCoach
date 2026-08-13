"""The deterministic longitudinal reasoning service.

This is the *single* implementation of "how is this member trending". The
workout pipeline, the Copilot and the MCP tools all read it, so a trend can
never differ depending on which surface asked - the failure mode where a chart
says one thing and a workout rationale says another.

It computes nothing that ``copilot.analytics`` already computes. Adherence,
sleep and session arithmetic are delegated, and this module's job is only to
turn those numbers into a small typed trajectory plus the two personalization
levers ranking is allowed to use.

Three boundaries are enforced here rather than documented and hoped for:

* **No clinical inference.** ``injury_trajectory`` copies the recorded injury
  status. Nothing derives "recovering" or "worsening" from adherence, sleep or
  RPE, because none of those support that conclusion.
* **No guessing.** Every branch that lacks data returns ``insufficient_data``.
* **No authority.** The output is consumed by ranking and composition only. The
  safety engine never receives it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.copilot import analytics
from app.domain.member import MemberContext
from app.domain.trajectory import (
    AdherenceTrajectory,
    InjuryTrajectory,
    MemberTrajectory,
    PersonalizationBias,
    ProgressionTrajectory,
    SleepTrajectory,
    TrainingLoadTrajectory,
)
from app.ontology.loader import Ontology

# --- thresholds --------------------------------------------------------------
# Named because a magic number in a personalization rule is a rule nobody can
# review. All are member-relative, not population norms.

MIN_ADHERENCE_OBSERVATIONS = 2
MIN_SESSIONS_FOR_LOAD = 2

LOAD_LOW_RATIO = 0.7
"""Below 70% of the member's own weekly session target counts as low."""

LOAD_HIGH_RATIO = 1.15
"""Above 115% of their own target counts as high."""

DAYS_PER_WEEK = 7.0

RECORDED_INJURY_STATES = {
    "recovering": "recovering",
    "improving": "recovering",
    "worsening": "worsening",
    "flare": "worsening",
    "flare-up": "worsening",
    "stable": "stable",
    "chronic": "stable",
}
"""Recorded status -> trajectory state. Anything unlisted stays ``unknown``.

A vocabulary rather than a guess: an unrecognised status is reported as unknown
instead of being bucketed into the nearest-looking state.
"""


@dataclass(frozen=True)
class MemberTrajectoryService:
    """Builds a :class:`MemberTrajectory` from the member graph.

    Takes the ontology so movement-family familiarity is resolved through the
    curated vocabulary rather than by matching exercise-name strings - the same
    reason "exclude deadlifts" resolves to a family instead of a substring.
    """

    ontology: Ontology

    def analyze(self, member: MemberContext) -> MemberTrajectory:
        adherence = self._adherence(member)
        sleep = self._sleep(member)
        load = self._training_load(member)
        injury = self._injury(member)
        progression = self._progression(adherence, sleep, load, injury)

        return MemberTrajectory(
            member_id=member.profile.id,
            adherence=adherence,
            sleep=sleep,
            training_load=load,
            progression=progression,
            injury_trajectory=injury,
            bias=self._bias(progression, load, adherence, member),
        )

    # --- signals ----------------------------------------------------------

    def _adherence(self, member: MemberContext) -> AdherenceTrajectory:
        trend = analytics.adherence_trend(member)
        if len(trend.values) < MIN_ADHERENCE_OBSERVATIONS:
            return AdherenceTrajectory(observations=len(trend.values))
        return AdherenceTrajectory(
            direction=trend.direction,  # type: ignore[arg-type]
            first=trend.first,
            latest=trend.latest,
            delta=trend.delta,
            observations=len(trend.values),
        )

    def _sleep(self, member: MemberContext) -> SleepTrajectory:
        trend = analytics.sleep_trend(member)
        return SleepTrajectory(
            direction=trend.direction,  # type: ignore[arg-type]
            average_recent=trend.average,
            nights=len(trend.values),
        )

    def _training_load(self, member: MemberContext) -> TrainingLoadTrajectory:
        """Completed sessions per week against the member's own stated target."""
        stats = analytics.session_stats(member)
        target = member.preferences.training_days_per_week

        average_minutes = (
            round(stats.total_minutes / stats.completed, 1) if stats.completed else None
        )
        base = TrainingLoadTrajectory(
            completed_sessions=stats.completed,
            target_sessions_per_week=target,
            average_session_minutes=average_minutes,
            average_rpe=stats.average_rpe,
        )

        weeks = _history_span_weeks(member)
        if stats.completed < MIN_SESSIONS_FOR_LOAD or weeks is None or not target:
            return base

        per_week = round(stats.completed / weeks, 2)
        ratio = round(per_week / target, 2)
        if ratio < LOAD_LOW_RATIO:
            state = "low"
        elif ratio > LOAD_HIGH_RATIO:
            state = "high"
        else:
            state = "moderate"

        return base.model_copy(
            update={
                "state": state,
                "sessions_per_week": per_week,
                "ratio_to_target": ratio,
            }
        )

    @staticmethod
    def _injury(member: MemberContext) -> InjuryTrajectory:
        """Copy the recorded injury status. Never derive it.

        Deriving a clinical trajectory from behavioural data is the single most
        tempting and least defensible inference available here: falling
        adherence and short sessions are equally consistent with a busy week.
        """
        active = [i for i in member.injuries if i.status]
        if not active:
            return InjuryTrajectory()

        injury = active[0]
        recorded = (injury.status or "").strip().lower()
        return InjuryTrajectory(
            state=RECORDED_INJURY_STATES.get(recorded, "unknown"),  # type: ignore[arg-type]
            source="recorded_status",
            injury_name=injury.region,
            recorded_status=injury.status,
            severity=injury.severity,
        )

    # --- derived state ----------------------------------------------------

    @staticmethod
    def _progression(
        adherence: AdherenceTrajectory,
        sleep: SleepTrajectory,
        load: TrainingLoadTrajectory,
        injury: InjuryTrajectory,
    ) -> ProgressionTrajectory:
        """Ordered rules, first match wins. Conservative by construction.

        The ordering matters: anything that argues for holding back is checked
        before anything that argues for pushing on, so a mixed picture resolves
        to the cautious answer rather than the optimistic one.
        """
        if adherence.direction == "insufficient_data" or load.state == "insufficient_data":
            return ProgressionTrajectory(
                state="insufficient_data",
                rationale=["Not enough adherence or session history to judge progression."],
            )

        reasons: list[str] = []

        if injury.state == "worsening":
            return ProgressionTrajectory(
                state="regress",
                rationale=[
                    f"Recorded injury status is worsening ({injury.recorded_status}).",
                ],
            )

        if adherence.direction == "declining":
            reasons.append(
                f"Adherence declining ({adherence.first:.0f}% to {adherence.latest:.0f}%)."
            )
        if load.state == "low":
            reasons.append(
                f"Training load low: {load.sessions_per_week}/week against a target of "
                f"{load.target_sessions_per_week}."
            )
        if sleep.direction == "declining":
            reasons.append(f"Sleep declining (avg {sleep.average_recent}h).")

        if reasons:
            return ProgressionTrajectory(state="hold", rationale=reasons)

        return ProgressionTrajectory(
            state="progress",
            rationale=[
                f"Adherence {adherence.direction} and training load {load.state}; "
                "no recovery signal argues for holding back."
            ],
        )

    def _bias(
        self,
        progression: ProgressionTrajectory,
        load: TrainingLoadTrajectory,
        adherence: AdherenceTrajectory,
        member: MemberContext,
    ) -> PersonalizationBias:
        """Turn progression state into the two levers ranking may use.

        Both levers move together on purpose. Independent knobs would multiply
        the states to reason about without adding expressive power at this
        scale.
        """
        familiar = self.familiar_movement_families(member)

        if progression.state in {"hold", "regress"}:
            return PersonalizationBias(
                volume_bias="conservative",
                novelty_bias="low",
                familiar_movement_families=familiar,
            )

        if (
            progression.state == "progress"
            and load.state == "high"
            and adherence.direction == "improving"
        ):
            return PersonalizationBias(
                volume_bias="ambitious",
                novelty_bias="high",
                familiar_movement_families=familiar,
            )

        return PersonalizationBias(
            volume_bias="standard",
            novelty_bias="standard",
            familiar_movement_families=familiar,
        )

    # --- familiarity ------------------------------------------------------

    def familiar_movement_families(self, member: MemberContext) -> list[str]:
        """Movement families the member has actually completed recently.

        Workout history stores display names ("KB Romanian Deadlift") that are
        not catalog ids, and **none** of them match a catalog exercise by name.
        Matching names would therefore find nothing at all. Instead each history
        name is matched against the curated movement-family aliases, longest
        alias first, which is exactly how "exclude deadlifts" reaches the hinge
        family.

        A name that matches nothing is left unresolved rather than guessed -
        "Hip Thrust", "Wall Sit" and "Banded Lateral Walk" have no family alias
        in the vocabulary and contribute nothing.
        """
        families: list[str] = []
        for session in member.workout_history:
            if not session.completed:
                continue
            for performance in session.exercises:
                family = self._family_for_name(performance.name)
                if family and family not in families:
                    families.append(family)
        return sorted(families)

    def _family_for_name(self, name: str) -> str | None:
        needle = name.strip().lower()
        if not needle:
            return None
        # Longest alias first so "romanian deadlift" wins over "deadlift", and
        # "split squat" over "squat".
        for alias, family_id in self._alias_index():
            if alias in needle:
                return family_id
        return None

    def _alias_index(self) -> list[tuple[str, str]]:
        pairs = [
            (alias, family.id)
            for family in self.ontology.movement_families.values()
            for alias in family.aliases
        ]
        pairs.sort(key=lambda pair: -len(pair[0]))
        return pairs


def _history_span_weeks(member: MemberContext) -> float | None:
    """Weeks covered by the recorded history window, inclusive of both ends.

    Returns ``None`` when a date is missing or unparseable, which propagates to
    ``insufficient_data`` rather than to a fabricated denominator.
    """
    dates: list[date] = []
    for session in member.workout_history:
        try:
            dates.append(date.fromisoformat(session.date))
        except (TypeError, ValueError):
            return None
    if len(dates) < 2:
        return None

    span_days = (max(dates) - min(dates)).days + 1
    return max(span_days / DAYS_PER_WEEK, 1.0 / DAYS_PER_WEEK)
