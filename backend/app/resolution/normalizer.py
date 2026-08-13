"""Text normalization for concept resolution.

Kept deliberately small and deterministic. Anything clever belongs in a later
resolver pass where it carries a confidence score that can be thresholded.
"""

from __future__ import annotations

import re

# Coach shorthand that is unambiguous in this domain. Expanded before matching
# so "DBs" and "dumbbells" collapse to the same normalized form.
ABBREVIATIONS = {
    "db": "dumbbell",
    "dbs": "dumbbell",
    "kb": "kettlebell",
    "kbs": "kettlebell",
    "bb": "barbell",
    "bw": "bodyweight",
    "rdl": "romanian deadlift",
    "ohp": "overhead press",
    "hiit": "high intensity interval training",
    "rom": "range of motion",
    "pfps": "patellofemoral pain syndrome",
    "doms": "delayed onset muscle soreness",
}

# Filler that carries no concept meaning. Removed only when a phrase has other
# content, so "her" alone never becomes an empty string.
STOPWORDS = {
    "a", "an", "the", "her", "his", "their", "she", "he", "they",
    "is", "are", "was", "were", "be", "been", "being",
    "some", "any", "only", "just", "please", "with", "and", "or",
    "of", "for", "to", "in", "on", "at", "by",
}

PLURAL_EXCEPTIONS = {"triceps", "biceps", "abs", "lats", "glutes", "quads", "hamstrings",
                     "calves", "obliques", "traps", "burpees"}

_PUNCT = re.compile(r"[^\w\s\-]")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """lowercase, strip punctuation, collapse whitespace, expand abbreviations."""
    if not text:
        return ""
    lowered = text.lower().strip()
    lowered = _PUNCT.sub(" ", lowered)
    lowered = _WS.sub(" ", lowered).strip()

    tokens = [ABBREVIATIONS.get(token, token) for token in lowered.split()]
    return " ".join(tokens).strip()


def strip_stopwords(text: str) -> str:
    tokens = [t for t in text.split() if t not in STOPWORDS]
    return " ".join(tokens) if tokens else text


def singularize(text: str) -> str:
    """Naive singularization that respects anatomy terms ending in 's'."""
    tokens = []
    for token in text.split():
        if token in PLURAL_EXCEPTIONS or len(token) <= 3:
            tokens.append(token)
        elif token.endswith("ies"):
            tokens.append(token[:-3] + "y")
        elif token.endswith("es") and token.endswith(("ches", "shes", "sses")):
            tokens.append(token[:-2])
        elif token.endswith("s") and not token.endswith("ss"):
            tokens.append(token[:-1])
        else:
            tokens.append(token)
    return " ".join(tokens)


def normalization_variants(text: str) -> list[str]:
    """Ordered candidate forms to try against the alias index.

    Most specific first so that an exact hit on the raw normalized form always
    beats a hit on an aggressively stripped form.
    """
    base = normalize(text)
    variants = [base]
    for candidate in (strip_stopwords(base), singularize(base), singularize(strip_stopwords(base))):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


LATERALITY = re.compile(r"\b(left|right|both|bilateral)\b")


def extract_laterality(text: str) -> str | None:
    """Pull "left"/"right" out of a phrase such as "left knee"."""
    match = LATERALITY.search(text.lower())
    if not match:
        return None
    value = match.group(1)
    return "bilateral" if value in {"both", "bilateral"} else value
