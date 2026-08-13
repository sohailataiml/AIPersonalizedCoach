"""Longitudinal member trajectory contracts.

One small typed model rather than a scatter of heuristics. Every field is
arithmetic over the member graph, computed in Python, and the LLM never
produces or revises one.

Three rules govern this module, and they are the reason it is deliberately
narrow:

1. **Personalization, not clinical truth.** A trajectory shapes *ordering* and
   *tone*. It never establishes safety, and the safety engine does not read it.
2. **Recorded, not inferred, for anything medical.** ``injury_trajectory`` is
   read verbatim from the member's recorded injury status. It is never derived
   from adherence, sleep or session data, because none of those support a
   clinical conclusion.
3. **Insufficient data is an answer.** Every signal has an explicit
   ``insufficient_data`` / ``unknown`` state and returns it rather than guessing
   from one observation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TrendDirection = Literal["improving", "declining", "flat", "insufficient_data"]
LoadState = Literal["low", "moderate", "high", "insufficient_data"]
ProgressionState = Literal["progress", "hold", "regress", "insufficient_data"]
InjuryTrajectoryState = Literal["recovering", "worsening", "stable", "unknown"]
VolumeBias = Literal["conservative", "standard", "ambitious"]
NoveltyBias = Literal["low", "standard", "high"]


class AdherenceTrajectory(BaseModel):
    direction: TrendDirection = "insufficient_data"
    first: float | None = None
    latest: float | None = None
    delta: float | None = None
    observations: int = 0


class SleepTrajectory(BaseModel):
    """Sleep direction and average only.

    Deliberately carries no "adequate / inadequate" judgement: the supplied data
    contains no target, and inventing a threshold would turn arithmetic into an
    unsupported health claim.
    """

    direction: TrendDirection = "insufficient_data"
    average_recent: float | None = None
    nights: int = 0


class TrainingLoadTrajectory(BaseModel):
    """Recent training volume, measured against the member's *own* target.

    Expressed relative to ``target_sessions_per_week`` from the member's stated
    preferences rather than any population norm, so "low" means "below what this
    member intended", which is a personalization fact rather than a health one.
    """

    state: LoadState = "insufficient_data"
    completed_sessions: int = 0
    sessions_per_week: float | None = None
    target_sessions_per_week: int | None = None
    ratio_to_target: float | None = None
    average_session_minutes: float | None = None
    average_rpe: float | None = None


class ProgressionTrajectory(BaseModel):
    state: ProgressionState = "insufficient_data"
    rationale: list[str] = Field(default_factory=list)
    """Ordered, human-readable reasons - the same strings provenance shows."""


class InjuryTrajectory(BaseModel):
    """Read from the recorded injury status. Never computed.

    ``source`` states where the value came from so a reader can tell a recorded
    clinical status from a derived one. It is always ``recorded_status`` today,
    and that is the point.
    """

    state: InjuryTrajectoryState = "unknown"
    source: Literal["recorded_status", "absent"] = "absent"
    injury_name: str | None = None
    recorded_status: str | None = None
    severity: str | None = None


class PersonalizationBias(BaseModel):
    """The only part of the trajectory that ranking and composition consume.

    Keeping the levers in one small object is what stops longitudinal reasoning
    from leaking into arbitrary places: a caller takes a bias, not a pile of
    metrics it might interpret differently.
    """

    volume_bias: VolumeBias = "standard"
    novelty_bias: NoveltyBias = "standard"
    familiar_movement_families: list[str] = Field(default_factory=list)
    """Movement families the member has actually trained recently."""


class MemberTrajectory(BaseModel):
    member_id: str
    adherence: AdherenceTrajectory = Field(default_factory=AdherenceTrajectory)
    sleep: SleepTrajectory = Field(default_factory=SleepTrajectory)
    training_load: TrainingLoadTrajectory = Field(default_factory=TrainingLoadTrajectory)
    progression: ProgressionTrajectory = Field(default_factory=ProgressionTrajectory)
    injury_trajectory: InjuryTrajectory = Field(default_factory=InjuryTrajectory)
    bias: PersonalizationBias = Field(default_factory=PersonalizationBias)

    @property
    def has_signal(self) -> bool:
        """True when at least one signal is strong enough to personalize on."""
        return (
            self.progression.state != "insufficient_data"
            or self.adherence.direction != "insufficient_data"
        )

    def summary_facts(self) -> list[str]:
        """Coach-facing one-liners, for provenance and the member-facts panel."""
        facts: list[str] = []

        if self.adherence.direction != "insufficient_data":
            delta = f"{self.adherence.delta:+.0f}pp" if self.adherence.delta else "no change"
            facts.append(
                f"Adherence {self.adherence.direction} over "
                f"{self.adherence.observations} weeks "
                f"({self.adherence.first:.0f}% to {self.adherence.latest:.0f}%, {delta})."
            )
        if self.sleep.direction != "insufficient_data" and self.sleep.average_recent:
            facts.append(
                f"Sleep {self.sleep.direction} across {self.sleep.nights} nights "
                f"(avg {self.sleep.average_recent}h)."
            )
        if self.training_load.state != "insufficient_data":
            facts.append(
                f"Training load {self.training_load.state}: "
                f"{self.training_load.completed_sessions} completed sessions, "
                f"{self.training_load.sessions_per_week}/week against a target of "
                f"{self.training_load.target_sessions_per_week}."
            )
        if self.progression.state != "insufficient_data":
            facts.append(f"Progression: {self.progression.state}.")
        if self.injury_trajectory.state != "unknown":
            facts.append(
                f"Injury trajectory: {self.injury_trajectory.state} "
                f"({self.injury_trajectory.injury_name}, recorded status - not inferred)."
            )
        return facts
