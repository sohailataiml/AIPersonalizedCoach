"""Exercise catalog domain models.

Field semantics are taken from the *actual* shape of data/exercises.json, not
from assumption. Two of them are counter-intuitive and are documented here
because the safety engine depends on reading them correctly:

``is_bilateral``
    In this dataset ``is_bilateral=True`` marks an exercise performed **one side
    at a time**, which therefore has a contralateral twin referenced by
    ``bilateral_pair_id``. It does NOT mean "uses both limbs". All 18 such rows
    carry a non-null ``side``; all 32 rows with ``is_bilateral=False`` have
    ``side=None``. We expose ``is_unilateral`` as the readable alias and keep the
    raw field for fidelity.

``side``
    Only ever ``left_arm`` / ``left_leg`` / ``left_side`` in the supplied
    catalog - the right-hand twins are not included. This matters: the sample
    member's injury is a **left** knee, so a ``left_leg`` exercise that loads the
    knee is loading the *injured* side specifically.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

Side = Literal["left_arm", "left_leg", "left_side"]
BodySide = Literal["left", "right", "bilateral"]


class Exercise(BaseModel):
    """One row of the supplied catalog, normalized but not reinterpreted."""

    id: str
    name: str
    muscle_groups: list[str] = Field(default_factory=list)
    joints_loaded: list[str] = Field(default_factory=list)
    movement_patterns: list[str] = Field(default_factory=list)
    equipment_required: list[str] = Field(default_factory=list)
    is_bilateral: bool = False
    side: Side | None = None
    priority_tier: int | None = None
    is_reps: bool = True
    is_duration: bool = False
    supports_weight: bool = False
    estimated_rep_duration: float | None = None
    bilateral_pair_id: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_unilateral(self) -> bool:
        """Readable alias for the dataset's inverted ``is_bilateral`` flag."""
        return self.is_bilateral or self.side is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def loaded_body_side(self) -> BodySide:
        """Which side of the body this variant loads.

        Drives side-aware injury reasoning: a left-knee injury penalises
        ``left_leg`` knee-loading variants harder than bilateral ones.
        """
        if self.side is None:
            return "bilateral"
        return "left"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_anatomy_data(self) -> bool:
        """False for the 2 catalog rows with an empty ``joints_loaded``.

        We cannot certify those as injury-safe, so the safety engine treats them
        conservatively rather than assuming "no joints listed = safe".
        """
        return bool(self.joints_loaded)


class ExerciseCandidate(BaseModel):
    """An exercise that survived safety filtering, with its ranking score."""

    exercise: Exercise
    score: float = 0.0
    rank_reasons: list[str] = Field(default_factory=list)