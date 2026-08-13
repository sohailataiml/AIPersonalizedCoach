"""Evaluation artifacts on disk.

A directory of JSON files, not a database. Evaluation output is append-only,
small, and most useful when it can be diffed and committed alongside the code
that produced it - three properties a table would take away.

    artifacts/evals/
      2026-08-13T001500Z-a1b2c3.json   full run, every case
      latest.json                      copy of the newest full run
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.domain.evaluation import EvaluationHistory, EvaluationRun, EvaluationSummary

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "evals"
LATEST_NAME = "latest.json"

#: Run ids become file names, so they must not be able to escape the directory.
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class EvaluationArtifactStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or DEFAULT_DIR

    # --- writing ----------------------------------------------------------

    def save(self, run: EvaluationRun) -> Path:
        """Write the run, then refresh ``latest.json``."""
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = run.model_dump(mode="json")

        path = self.directory / f"{self._safe_name(run.run_id)}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (self.directory / LATEST_NAME).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        return path

    # --- reading ----------------------------------------------------------

    def latest(self) -> EvaluationRun | None:
        path = self.directory / LATEST_NAME
        if not path.exists():
            return None
        return self._load(path)

    def get(self, run_id: str) -> EvaluationRun | None:
        path = self.directory / f"{self._safe_name(run_id)}.json"
        if not path.exists():
            return None
        return self._load(path)

    def history(self, limit: int = 10) -> EvaluationHistory:
        """Recent runs, newest first, as compact summaries.

        Reads whole files because a run is a few hundred KB and this is a local
        developer surface. A corrupt or partially written file is skipped rather
        than failing the whole listing.
        """
        summaries: list[EvaluationSummary] = []
        for path in sorted(self.directory.glob("*.json"), reverse=True):
            if path.name == LATEST_NAME:
                continue
            run = self._load(path)
            if run is None:
                continue
            summaries.append(
                EvaluationSummary(
                    run_id=run.run_id,
                    started_at=run.started_at,
                    status=run.status,
                    total_cases=run.total_cases,
                    passed_cases=run.passed_cases,
                    failed_cases=run.failed_cases,
                    unsafe_escapes=run.unsafe_escapes,
                    p95_ms=run.latency.p95_ms,
                    duration_ms=run.duration_ms,
                )
            )
            if len(summaries) >= limit:
                break

        return EvaluationHistory(runs=summaries, count=len(summaries))

    # --- internals --------------------------------------------------------

    @staticmethod
    def _safe_name(run_id: str) -> str:
        if not SAFE_RUN_ID.match(run_id):
            raise ValueError(f"unsafe run id: {run_id!r}")
        return run_id

    @staticmethod
    def _load(path: Path) -> EvaluationRun | None:
        try:
            return EvaluationRun.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a bad artifact must not break the listing
            return None
