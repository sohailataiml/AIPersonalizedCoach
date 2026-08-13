"""Member-context domain models.

These mirror the supplied ``data/member-context.json`` exactly - no invented
fields. Where the assessment's ARCHITECTURE.md anticipated a node type that the
real data does not carry (e.g. a standalone ``Workout`` template distinct from a
session), we model what exists rather than fabricating structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemberProfile(BaseModel):
    id: str
    name: str
    age: int | None = None
    sex: str | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
    timezone: str | None = None
    member_since: str | None = None
    coach_id: str | None = None
    tier: str | None = None


class Goal(BaseModel):
    id: str
    text: str
    priority: int = 3
    target_date: str | None = None


class Preferences(BaseModel):
    preferred_session_minutes: int | None = None
    training_days_per_week: int | None = None
    preferred_days: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    notes: str | None = None


class Injury(BaseModel):
    """A member injury. ``joint`` and ``region`` are the bridge into KG1.

    ``notes`` carries clinically meaningful free text ("avoid deep knee flexion
    under load and plyometrics") which we resolve into explicit contraindication
    edges at ingest time rather than passing to the LLM as a prompt hint.
    """

    id: str
    region: str
    joint: str | None = None
    status: str | None = None
    severity: str | None = None
    since: str | None = None
    notes: str | None = None
    snomedct_hint: str | None = None


class ExercisePerformance(BaseModel):
    """One exercise name recorded inside a completed session.

    The catalog is not referenced by id in ``workout_history`` - history stores
    display names ("KB Romanian Deadlift") that do not always exist in
    exercises.json. We keep the raw name and resolve opportunistically.
    """

    name: str
    resolved_exercise_id: str | None = None


class WorkoutSession(BaseModel):
    date: str
    title: str
    planned: bool = True
    completed: bool = False
    duration_min: int = 0
    rpe: int | None = None
    exercises: list[ExercisePerformance] = Field(default_factory=list)


class AdherenceObservation(BaseModel):
    week_of: str
    pct: float


class Adherence(BaseModel):
    weekly_completion_pct: list[AdherenceObservation] = Field(default_factory=list)
    trend: str | None = None


class WeightObservation(BaseModel):
    date: str
    kg: float


class Biomarkers(BaseModel):
    resting_hr_bpm: int | None = None
    hrv_ms: int | None = None
    sleep_hours_last_7_days: list[float] = Field(default_factory=list)
    weight_trend_kg: list[WeightObservation] = Field(default_factory=list)


class BloodPanel(BaseModel):
    date: str | None = None
    ldl_mg_dl: float | None = None
    hdl_mg_dl: float | None = None
    triglycerides_mg_dl: float | None = None
    hba1c_pct: float | None = None
    vitamin_d_ng_ml: float | None = None
    ferritin_ng_ml: float | None = None
    crp_mg_l: float | None = None


class DexaScan(BaseModel):
    date: str | None = None
    body_fat_pct: float | None = None
    lean_mass_kg: float | None = None
    fat_mass_kg: float | None = None
    bone_density_z_score: float | None = None
    visceral_fat_cm2: float | None = None


class Labs(BaseModel):
    blood_panel: BloodPanel | None = None
    dexa_scan: DexaScan | None = None


class ChatAttachment(BaseModel):
    type: str
    caption: str | None = None


class ChatMessage(BaseModel):
    ts: str
    sender: str = Field(alias="from")
    text: str
    attachments: list[ChatAttachment] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MorningTask(BaseModel):
    type: str
    text: str


class ChurnRisk(BaseModel):
    level: str
    reasons: list[str] = Field(default_factory=list)


class CoachBrief(BaseModel):
    generated_for: str | None = None
    morning_tasks: list[MorningTask] = Field(default_factory=list)
    churn_risk: ChurnRisk | None = None


class MemberContext(BaseModel):
    """The whole member world, as ingested into KG2."""

    profile: MemberProfile
    goals: list[Goal] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    equipment_available: list[str] = Field(default_factory=list)
    injuries: list[Injury] = Field(default_factory=list)
    workout_history: list[WorkoutSession] = Field(default_factory=list)
    adherence: Adherence = Field(default_factory=Adherence)
    biomarkers: Biomarkers = Field(default_factory=Biomarkers)
    labs: Labs = Field(default_factory=Labs)
    chat_history: list[ChatMessage] = Field(default_factory=list)
    coach_brief: CoachBrief = Field(default_factory=CoachBrief)


class MemberSummary(BaseModel):
    """Coach-facing header payload. Never the raw source JSON."""

    id: str
    name: str
    tier: str | None = None
    age: int | None = None
    primary_goal: str | None = None
    goals: list[Goal] = Field(default_factory=list)
    active_injuries: list[Injury] = Field(default_factory=list)
    equipment_available: list[str] = Field(default_factory=list)
    latest_adherence_pct: float | None = None
    adherence_trend: str | None = None
    churn_risk_level: str | None = None
    churn_risk_reasons: list[str] = Field(default_factory=list)
    avg_sleep_hours: float | None = None
    preferred_session_minutes: int | None = None