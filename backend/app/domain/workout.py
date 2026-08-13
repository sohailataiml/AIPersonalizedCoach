"""Workout request / plan contracts.

``LLMWorkoutDraft`` is deliberately separate from ``GeneratedWorkout``: the draft
is untrusted model output; the generated workout is what survived the
deterministic post-generation gate.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SectionName = Literal["warmup", "main", "cooldown"]


class WorkoutRequest(BaseModel):
    member_id: str
    prompt: str
    duration_minutes: int = Field(default=45, ge=10, le=120)
    duration_is_explicit: bool = False
    """Take ``duration_minutes`` as final, ignoring any duration in the prompt.

    Needed by adjustment: an adjusted request carries the original prompt *and*
    the new instruction, so the prompt contains two durations ("45-minute ...
    make it 30 minutes"). The caller resolves which one wins deterministically
    and sets this, rather than leaving a regex to pick whichever came first.
    """


class WorkoutIntent(BaseModel):
    """Parsed coach intent. Extraction may use the LLM; it decides no safety."""

    requested_focus: list[str] = Field(default_factory=list)
    explicit_exclusions: list[str] = Field(default_factory=list)
    equipment_mentions: list[str] = Field(default_factory=list)
    injury_mentions: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    duration_minutes: int = 45
    equipment_is_restrictive: bool = False
    """True when the coach phrased equipment as a closed set ("only DBs")."""


class WorkoutExercise(BaseModel):
    exercise_id: str
    name: str
    sets: int | None = None
    reps: str | None = None
    duration_seconds: int | None = None
    rest_seconds: int | None = None
    rationale: str = ""
    coaching_note: str | None = None
    substituted_for: str | None = None
    """Set when the post-generation gate swapped an unsafe pick for this one."""


class WorkoutSection(BaseModel):
    name: SectionName
    exercises: list[WorkoutExercise] = Field(default_factory=list)


class LLMWorkoutDraft(BaseModel):
    """Untrusted structured output from the model."""

    title: str = "Workout"
    sections: list[WorkoutSection] = Field(default_factory=list)

    def all_exercises(self) -> list[WorkoutExercise]:
        return [ex for section in self.sections for ex in section.exercises]


class GeneratedWorkout(BaseModel):
    title: str
    duration_minutes: int
    sections: list[WorkoutSection] = Field(default_factory=list)
    summary: str | None = None

    def all_exercises(self) -> list[WorkoutExercise]:
        return [ex for section in self.sections for ex in section.exercises]


class PostValidationReport(BaseModel):
    """Evidence that the LLM could not bypass the graph."""

    passed: bool = True
    checked_exercise_ids: list[str] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)
    replacements: list[dict] = Field(default_factory=list)
    hallucinated_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)