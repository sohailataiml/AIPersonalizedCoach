"""Coach request parsing.

Deterministic by default. The prompt is split into **clauses**, each clause is
classified by the cues it contains (exclusion / negation / restriction /
injury), and only then are concept spans resolved inside it. Attributing
polarity at clause level rather than by proximity is what stops
"no barbell, only dumbbells and a kettlebell" from excluding the kettlebell.

An LLM extractor is permitted here and can be layered on, because parsing intent
does not decide safety - every extracted phrase still has to survive the
resolver and then the graph. If a model invented "no knee issues", the member
graph would still say otherwise and the safety engine would still win.
"""

from __future__ import annotations

import re

from app.domain.resolution import ResolvedConcept
from app.domain.workout import WorkoutIntent
from app.resolution.normalizer import STOPWORDS, normalize
from app.resolution.resolver import ConceptResolver

MAX_SPAN_TOKENS = 3

DURATION_RE = re.compile(r"(\d{1,3})\s*(?:-|\s)?\s*(?:minute|minutes|min|mins)\b", re.I)

EXCLUSION_CUES = re.compile(
    r"\b(?:exclude[sd]?|excluding|avoid(?:ing)?|without|skip|leave out|drop|"
    r"no more|don'?t (?:use|do|include)|not doing)\b",
    re.I,
)
NEGATION_CUES = re.compile(
    r"\b(?:no|none|doesn'?t have|does not have|hasn'?t got|lacks|out of)\b", re.I
)
RESTRICTIVE_CUES = re.compile(r"\b(?:only|just|nothing but|all (?:she|he|they) ha[sve]+)\b", re.I)
INJURY_CUES = re.compile(
    r"\b(?:injur\w*|bothering|hurts?|hurting|pain(?:ful)?|sore|tweaked|flare[- ]?up|"
    r"acting up|recovering|rehab|issues?|bad|niggl\w+|tender)\b",
    re.I,
)

# Words that introduce a constraint and must never end up inside a concept span.
CUE_TOKENS = {
    "exclude", "excludes", "excluded", "excluding", "avoid", "avoiding", "without",
    "skip", "drop", "no", "none", "not", "only", "just", "but", "she", "he", "they",
    "her", "his", "their", "has", "have", "is", "are", "bothering", "hurts", "hurting",
    "pain", "painful", "sore", "create", "build", "make", "workout", "session", "plan",
    "give", "want", "need", "please", "with", "and", "or", "a", "an", "the",
}

CLAUSE_SPLIT = re.compile(r"[.;,!?\n]+|\bbut\b|\bthough\b|\bhowever\b", re.I)


def parse_intent(
    prompt: str,
    duration_minutes: int,
    resolver: ConceptResolver,
) -> tuple[WorkoutIntent, list[ResolvedConcept]]:
    """Return the parsed intent plus every resolution attempt (for the UI)."""
    intent = WorkoutIntent(duration_minutes=duration_minutes)

    duration_match = DURATION_RE.search(prompt)
    if duration_match:
        intent.duration_minutes = int(duration_match.group(1))

    intent.equipment_is_restrictive = bool(RESTRICTIVE_CUES.search(prompt))

    resolved: list[ResolvedConcept] = []
    by_concept: dict[str, ResolvedConcept] = {}

    for clause in _clauses(prompt):
        flags = _classify(clause)
        for concept in _resolve_spans(clause, resolver):
            assert concept.canonical_id is not None
            previous = by_concept.get(concept.canonical_id)
            if previous is not None and previous.confidence >= concept.confidence:
                continue
            if previous is not None:
                resolved.remove(previous)
                _unbucket(intent, previous)

            by_concept[concept.canonical_id] = concept
            resolved.append(concept)
            _bucket(intent, concept, flags)

    _record_unresolved_clinical_phrases(prompt, resolver, resolved)
    return intent, resolved


# --- clause handling ---------------------------------------------------------


def _clauses(prompt: str) -> list[str]:
    return [c.strip() for c in CLAUSE_SPLIT.split(prompt) if c and c.strip()]


class _Flags:
    __slots__ = ("exclusion", "negation", "restrictive", "injury")

    def __init__(self, exclusion: bool, negation: bool, restrictive: bool, injury: bool) -> None:
        self.exclusion = exclusion
        self.negation = negation
        self.restrictive = restrictive
        self.injury = injury


def _classify(clause: str) -> _Flags:
    return _Flags(
        exclusion=bool(EXCLUSION_CUES.search(clause)),
        negation=bool(NEGATION_CUES.search(clause)),
        restrictive=bool(RESTRICTIVE_CUES.search(clause)),
        injury=bool(INJURY_CUES.search(clause)),
    )


# --- span extraction ---------------------------------------------------------


def _resolve_spans(clause: str, resolver: ConceptResolver) -> list[ResolvedConcept]:
    """Longest-first, non-overlapping resolved spans within one clause.

    Cue tokens are stripped from candidate spans so "exclude deadlifts" yields
    the span "deadlifts" - the cue governs the clause, it is not part of the
    concept.
    """
    tokens = [
        (m.group(0), m.start(), m.end())
        for m in re.finditer(r"[\w\-']+", clause)
        if m.group(0).lower() not in CUE_TOKENS
    ]

    candidates: list[tuple[str, int, int]] = []
    for i in range(len(tokens)):
        for n in range(1, MAX_SPAN_TOKENS + 1):
            if i + n > len(tokens):
                break
            # Only join tokens that are actually adjacent in the source text.
            chunk = tokens[i : i + n]
            if any(
                clause[chunk[k][2] : chunk[k + 1][1]].strip(" -")
                for k in range(len(chunk) - 1)
            ):
                break
            candidates.append((clause[chunk[0][1] : chunk[-1][2]], chunk[0][1], chunk[-1][2]))

    candidates.sort(key=lambda s: (-len(s[0].split()), s[1]))

    accepted: list[ResolvedConcept] = []
    claimed: list[tuple[int, int]] = []
    for span, start, end in candidates:
        if any(start < e and end > s for s, e in claimed):
            continue
        normalized = normalize(span)
        if not normalized or all(t in STOPWORDS for t in normalized.split()):
            continue

        concept = resolver.resolve(span)
        if not concept.is_resolved:
            continue
        claimed.append((start, end))
        accepted.append(concept)

    return accepted


# --- bucketing ---------------------------------------------------------------


def _bucket(intent: WorkoutIntent, concept: ResolvedConcept, flags: _Flags) -> None:
    text = concept.source_text
    concept_type = concept.concept_type

    if concept_type == "equipment":
        # A clause that negates or excludes removes the item; otherwise the
        # coach is declaring what IS available.
        if flags.exclusion or flags.negation:
            intent.explicit_exclusions.append(text)
        else:
            intent.equipment_mentions.append(text)
        return

    if concept_type == "movement_pattern":
        if flags.exclusion or flags.negation:
            intent.explicit_exclusions.append(text)
        else:
            intent.requested_focus.append(text)
        return

    if concept_type == "injury_condition":
        intent.injury_mentions.append(text)
        return

    if concept_type == "anatomy":
        if flags.injury:
            intent.injury_mentions.append(text)
        else:
            intent.requested_focus.append(text)
        return

    if concept_type == "muscle":
        intent.requested_focus.append(text)


def _unbucket(intent: WorkoutIntent, concept: ResolvedConcept) -> None:
    for bucket in (
        intent.requested_focus,
        intent.explicit_exclusions,
        intent.equipment_mentions,
        intent.injury_mentions,
        intent.preferences,
    ):
        if concept.source_text in bucket:
            bucket.remove(concept.source_text)


# --- unresolved reporting ----------------------------------------------------


def _record_unresolved_clinical_phrases(
    prompt: str,
    resolver: ConceptResolver,
    resolved: list[ResolvedConcept],
) -> None:
    """Surface clinical-sounding phrases we could NOT resolve.

    Silently dropping "her thingy feels weird" is how a system quietly loses a
    safety-relevant signal, so it is reported as an explicit unresolved concept
    for the coach to see rather than discarded.
    """
    for clause in _clauses(prompt):
        if not INJURY_CUES.search(clause):
            continue
        if any(c.is_resolved and c.source_text.lower() in clause.lower() for c in resolved):
            continue
        attempt = resolver.resolve(clause)
        if not attempt.is_resolved and not any(r.source_text == clause for r in resolved):
            resolved.append(attempt)
