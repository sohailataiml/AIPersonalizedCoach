"""Graph connection and idempotent bootstrap.

Owned by application startup rather than a separate Render job, for one
practical reason: a Render disk is reachable only by the service it is attached
to, so any bootstrapper has to go over Bolt anyway. Doing it in the FastAPI
lifespan means one code path seeds locally, in CI and on Render, and the thing
that verifies the seed is the thing that will serve the queries.

Two properties this module exists to guarantee:

* **Idempotent.** Seeding writes with MERGE on stable keys, and a version
  marker lets a warm database skip the write entirely. Redeploying never
  duplicates a node, never duplicates a relationship, and never wipes.
* **Honest about failure.** In ``neo4j`` mode there is no silent fall back to
  the in-memory backend. Swapping the storage engine underneath a *safety*
  system because a database was slow to boot would be the worst kind of
  helpfulness. The service reports itself unready instead.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings
from app.ingestion.exercises import load_exercises
from app.ontology.loader import Ontology

logger = logging.getLogger(__name__)

#: Bumped when the seeded shape changes. A warm database whose marker matches
#: is left alone; anything else is re-merged (never wiped).
SEED_VERSION = "2026.08.13-1"

#: Counts the assessment specifies. A mis-seeded graph fails loudly here rather
#: than quietly under-filtering in the safety engine later.
EXPECTED: dict[str, int] = {
    "exercises": 50,
    "muscles": 19,
    "movement_patterns": 36,
    "equipment": 32,
    "catalog_joints": 9,
}

REQUIRED_EDGES = ("edge:STRESSES", "edge:REQUIRES", "edge:PART_OF", "edge:CONTRAINDICATES")


class GraphBackendUnavailableError(RuntimeError):
    """Raised when ``GRAPH_BACKEND=neo4j`` is set but Neo4j cannot be reached."""


@dataclass
class BootstrapReport:
    backend: str
    reachable: bool = False
    seeded: bool = False
    """True when the graph is present and verified - whether we wrote it now."""
    wrote: bool = False
    """True only when this process actually merged data."""
    seed_version: str | None = None
    attempts: int = 0
    duration_ms: float = 0.0
    problems: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def verify(stats: dict[str, int], exercises_path: Path) -> list[str]:
    """Check a seeded graph against the counts the assessment specifies."""
    problems: list[str] = []

    def check(key: str, expected: int) -> None:
        actual = stats.get(key, 0)
        if actual != expected:
            problems.append(f"{key}: expected {expected}, found {actual}")

    check("node:Exercise", EXPECTED["exercises"])
    check("node:Muscle", EXPECTED["muscles"])
    check("node:MovementPattern", EXPECTED["movement_patterns"])
    check("node:Equipment", EXPECTED["equipment"])

    # The 9 catalog joints must all be represented, though the curated anatomy
    # hierarchy deliberately adds more regions (e.g. the patellofemoral joint).
    catalog_joints = {
        joint for exercise in load_exercises(exercises_path) for joint in exercise.joints_loaded
    }
    if len(catalog_joints) != EXPECTED["catalog_joints"]:
        problems.append(
            f"catalog joints: expected {EXPECTED['catalog_joints']}, "
            f"found {len(catalog_joints)}"
        )
    if stats.get("node:AnatomicalRegion", 0) < EXPECTED["catalog_joints"]:
        problems.append("AnatomicalRegion count is below the number of catalog joints")

    for edge in REQUIRED_EDGES:
        if stats.get(edge, 0) == 0:
            problems.append(f"{edge}: no edges created")

    return problems


def safe_target(uri: str) -> str:
    """A log-safe rendering of the Bolt target: scheme and host only.

    Credentials are passed separately today, but a URI is exactly the field
    someone later embeds them in, so nothing beyond scheme/host/port is ever
    logged.
    """
    try:
        parts = urlsplit(uri)
        return f"{parts.scheme}://{parts.hostname or '?'}:{parts.port or '?'}"
    except ValueError:  # pragma: no cover - defensive
        return "<unparseable>"


def connect_with_retry(
    settings: Settings,
    ontology: Ontology,
    *,
    sleep=time.sleep,
) -> tuple[Any, int]:
    """Connect to Neo4j with bounded exponential backoff.

    FastAPI can start before Neo4j finishes booting, so a first failure is
    expected rather than fatal. Attempts are bounded - an unbounded retry would
    turn a misconfiguration into a service that never starts and never says
    why.
    """
    from app.graph.neo4j_repository import Neo4jGraphRepository

    attempts = max(1, settings.neo4j_connect_attempts)
    delay = max(0.0, settings.neo4j_connect_backoff_seconds)
    target = safe_target(settings.bolt_uri)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            repository = Neo4jGraphRepository.connect(
                settings.bolt_uri,
                settings.neo4j_user,
                settings.neo4j_password,
                settings.neo4j_database,
                settings.exercises_path,
                settings.member_context_path,
                ontology,
                connect_timeout_seconds=settings.neo4j_connect_timeout_seconds,
            )
            logger.info("neo4j connected target=%s attempt=%d", target, attempt)
            return repository, attempt
        except Exception as exc:  # noqa: BLE001 - any driver error is a retry
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning(
                "neo4j unreachable target=%s attempt=%d/%d retry_in=%.1fs error=%s",
                target,
                attempt,
                attempts,
                delay,
                type(exc).__name__,
            )
            sleep(delay)
            delay = min(delay * 2, settings.neo4j_connect_max_backoff_seconds)

    raise GraphBackendUnavailableError(
        f"Neo4j unreachable at {target} after {attempts} attempt(s): "
        f"{type(last_error).__name__ if last_error else 'unknown error'}"
    )


def ensure_seeded(repository: Any, settings: Settings) -> BootstrapReport:
    """Seed the graph if needed, verify it either way. Never destructive.

    Three outcomes:

    * already seeded at this version -> verified, nothing written;
    * empty or stale -> merged in place (``wipe=False``) and verified;
    * verification fails -> reported, and readiness stays false.
    """
    started = time.perf_counter()
    report = BootstrapReport(backend="neo4j")

    try:
        stats = repository.stats()
        report.reachable = True
    except Exception as exc:  # noqa: BLE001
        report.problems.append(f"stats query failed: {type(exc).__name__}")
        report.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return report

    current_version = _read_seed_version(repository)
    already = current_version == SEED_VERSION and not verify(
        stats, settings.exercises_path
    )

    if already:
        logger.info("graph already seeded version=%s - skipping bootstrap", SEED_VERSION)
    else:
        logger.info(
            "bootstrapping graph version=%s (found=%s) - merge, no wipe",
            SEED_VERSION,
            current_version or "unseeded",
        )
        # wipe=False is the whole point: a redeploy merges onto the existing
        # graph rather than resetting a database a reviewer may be looking at.
        stats = repository.seed(wipe=False)
        _write_seed_version(repository)
        report.wrote = True

    report.stats = stats
    report.problems = verify(stats, settings.exercises_path)
    report.seeded = not report.problems
    report.seed_version = SEED_VERSION if report.seeded else current_version
    report.duration_ms = round((time.perf_counter() - started) * 1000, 2)

    if report.problems:
        logger.error("graph verification failed: %s", "; ".join(report.problems))
    else:
        logger.info(
            "graph ready nodes=%d version=%s wrote=%s in %.0fms",
            sum(v for k, v in stats.items() if k.startswith("node:")),
            SEED_VERSION,
            report.wrote,
            report.duration_ms,
        )
    return report


# --- seed marker -------------------------------------------------------------


def _read_seed_version(repository: Any) -> str | None:
    reader = getattr(repository, "read_seed_version", None)
    return reader() if callable(reader) else None


def _write_seed_version(repository: Any) -> None:
    writer = getattr(repository, "record_seed_version", None)
    if not callable(writer):
        return
    try:
        writer(SEED_VERSION)
    except Exception as exc:  # noqa: BLE001 - the marker is an optimisation
        logger.warning("could not record seed marker: %s", type(exc).__name__)
