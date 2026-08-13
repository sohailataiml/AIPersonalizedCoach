"""Safety policy constants and severity rules.

Policy is separated from the engine so a clinician could review *what* the
system considers unsafe without reading traversal code. In production these
would be versioned, reviewed, and configurable per condition.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- score adjustments -------------------------------------------------------
# Negative numbers down-rank. Exclusion is a status, not a score.
PENALTY_LOADED_INJURY_REGION = -35.0
PENALTY_UNLOADED_INJURY_REGION = -8.0
PENALTY_CONTRAINDICATED_RECOVERING = -55.0
PENALTY_INJURED_SIDE = -25.0
PENALTY_UNKNOWN_ANATOMY = -10.0
PENALTY_PREFERENCE_DISLIKE = -15.0

BONUS_GOAL_ALIGNED = 12.0
BONUS_FOCUS_MATCH = 25.0
BONUS_EQUIPMENT_PREFERRED = 5.0
PENALTY_RECENTLY_PERFORMED = -6.0

# When the coach names a focus ("lower-body"), everything outside that focus is
# off-brief. Without this the arithmetic misfires in exactly the case that
# matters most: an injury penalty of -35..-55 on every lower-body option would
# float untouched upper-body work to the top, and a request for a lower-body
# session would quietly return an upper-body one. Mobility and regeneration work
# is exempt because it is always legitimate warmup/cooldown material.
PENALTY_OFF_FOCUS = -30.0

# Severity/status values that make a contraindicated movement a hard exclusion
# rather than a heavy down-rank.
ACUTE_STATUSES = {"acute", "flare", "flare-up", "active", "new"}
SEVERE_SEVERITIES = {"moderate", "severe", "high"}

# Movement families that are never merely "down-ranked" for a joint injury:
# impact loading is categorically unsafe for an irritated joint, and the sample
# member's own clinical note says "avoid ... plyometrics".
ALWAYS_EXCLUDED_FAMILIES = {"plyometric"}

# Patterns that represent unloaded/restorative work. A knee "stress" edge from a
# mobility drill is not the same clinical risk as a loaded squat, so we penalize
# it lightly instead of removing useful warmup and cooldown options.
LOW_LOAD_PATTERN_PREFIXES = (
    "mobility",
    "regen",
    "yoga",
    "massage",
    "isometric",
    "balance",
)


@dataclass(frozen=True)
class InjurySeverityPolicy:
    """How aggressively to act on a given injury."""

    hard_exclude_contraindicated: bool
    """True when a contraindicated movement pattern is removed outright."""

    penalty_contraindicated: float
    """Applied when the pattern is down-ranked instead of excluded."""


def policy_for(severity: str | None, status: str | None) -> InjurySeverityPolicy:
    """Choose a policy from the injury's recorded severity and status.

    The sample member is ``mild`` / ``recovering`` and explicitly "cleared for
    low-impact loading", so contraindicated *loading* patterns are down-ranked
    with a coaching caveat rather than removed - removing them entirely would
    leave almost nothing trainable and would not reflect the clinical note.
    Impact/plyometric work is still hard-excluded regardless (see
    ``ALWAYS_EXCLUDED_FAMILIES``).
    """
    normalized_status = (status or "").strip().lower()
    normalized_severity = (severity or "").strip().lower()

    is_acute = normalized_status in ACUTE_STATUSES or normalized_severity in SEVERE_SEVERITIES
    if is_acute:
        return InjurySeverityPolicy(
            hard_exclude_contraindicated=True,
            penalty_contraindicated=PENALTY_CONTRAINDICATED_RECOVERING,
        )
    return InjurySeverityPolicy(
        hard_exclude_contraindicated=False,
        penalty_contraindicated=PENALTY_CONTRAINDICATED_RECOVERING,
    )


def is_low_load_pattern(pattern: str) -> bool:
    lowered = pattern.strip().lower()
    return lowered.startswith(LOW_LOAD_PATTERN_PREFIXES)
