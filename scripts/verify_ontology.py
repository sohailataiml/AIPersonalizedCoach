#!/usr/bin/env python
"""Audit every ontology mapping against the published terminology server.

    python scripts/verify_ontology.py            # offline structural audit
    python scripts/verify_ontology.py --live     # + resolve every code at NCI EVS
    python scripts/verify_ontology.py --live --json

Why this exists
---------------
A SNOMED CT code in a YAML file is a claim, and a claim nobody re-checks decays
into fiction. An earlier revision of ``mappings.yaml`` carried eleven codes all
marked ``status: verified``; five of them did not survive contact with the
terminology server - three did not exist at all, and two resolved to a protozoan
and a plant. A fabricated identifier is worse than a missing one, because it
looks authoritative in a provenance trace.

The offline pass runs anywhere and is what the test suite asserts on. The
``--live`` pass is the one that actually re-verifies the claims, and it is
deliberately opt-in so the tests never depend on the network.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ontology.loader import Ontology, OntologyGrounding, get_ontology  # noqa: E402

TIMEOUT_SECONDS = 45
MAX_WORKERS = 8


@dataclass(frozen=True)
class Finding:
    local_id: str
    level: str  # "ok" | "warn" | "fail"
    message: str

    @property
    def failed(self) -> bool:
        return self.level == "fail"


# --- offline audit -----------------------------------------------------------


def audit_offline(ontology: Ontology) -> list[Finding]:
    """Structural checks that need no network.

    These catch the mistakes that are cheap to make while editing YAML: a code
    without a predicate, a source that was never declared, an "unmapped" entry
    that quietly grew a code.
    """
    findings: list[Finding] = []
    seen_codes: dict[str, str] = {}

    for grounding in ontology.groundings():
        findings.extend(_audit_one(grounding, ontology, seen_codes))

    return findings


def _audit_one(
    grounding: OntologyGrounding,
    ontology: Ontology,
    seen_codes: dict[str, str],
) -> list[Finding]:
    out: list[Finding] = []
    local_id = grounding.local_id

    if not grounding.is_grounded:
        if grounding.code:
            out.append(
                Finding(local_id, "fail", "listed as unmapped but carries a code")
            )
        elif not grounding.evidence:
            out.append(
                Finding(local_id, "fail", "unmapped with no recorded reason")
            )
        else:
            out.append(Finding(local_id, "ok", "unmapped, reason recorded"))
        return out

    assert grounding.source and grounding.code

    if grounding.source not in ontology.sources:
        out.append(
            Finding(local_id, "fail", f"undeclared ontology source {grounding.source!r}")
        )
    if not grounding.uri:
        out.append(Finding(local_id, "fail", "no dereferenceable URI could be built"))
    if not grounding.evidence:
        out.append(Finding(local_id, "fail", "grounded but carries no evidence string"))
    if not grounding.term:
        out.append(Finding(local_id, "warn", "no external term recorded"))
    if not grounding.version:
        out.append(Finding(local_id, "warn", "no mapping version recorded"))

    key = f"{grounding.source}:{grounding.code}"
    # Two local concepts sharing one external code is a modelling smell, not an
    # error - flag it so it is a decision rather than an accident.
    if key in seen_codes:
        out.append(
            Finding(local_id, "warn", f"shares {key} with {seen_codes[key]}")
        )
    else:
        seen_codes[key] = local_id

    if not any(f.level in {"fail", "warn"} for f in out):
        out.append(Finding(local_id, "ok", f"{key} {grounding.relation}"))
    return out


# --- live audit --------------------------------------------------------------


def _fetch(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _verify_live(grounding: OntologyGrounding, ontology: Ontology) -> Finding:
    """Resolve one code and confirm it denotes what we claim it denotes."""
    source = ontology.sources.get(grounding.source or "")
    if source is None or not source.api_template or not grounding.code:
        return Finding(grounding.local_id, "warn", "no API template for this source")

    url = source.api_template.format(code=grounding.code)
    try:
        payload = _fetch(url)
    except Exception as exc:  # noqa: BLE001 - a transport failure is not a mapping failure
        return Finding(grounding.local_id, "warn", f"lookup failed: {exc}")

    if payload is None:
        return Finding(
            grounding.local_id, "fail", f"{grounding.code} does not exist in {source.id}"
        )
    if payload.get("active") is False:
        return Finding(
            grounding.local_id, "fail", f"{grounding.code} is inactive in {source.id}"
        )

    names = {payload.get("name", "")} | {
        synonym.get("name", "") for synonym in payload.get("synonyms") or []
    }
    normalized = {name.strip().lower() for name in names if name}
    claimed = (grounding.term or "").strip().lower()

    # The recorded term must be the concept's preferred term or one of its
    # synonyms. This is the check that would have caught "Hexamita" being
    # recorded as "Gluteal muscle structure".
    if claimed and claimed not in normalized:
        return Finding(
            grounding.local_id,
            "fail",
            f"{grounding.code} resolves to {payload.get('name')!r}, "
            f"not the recorded {grounding.term!r}",
        )

    return Finding(
        grounding.local_id, "ok", f"{grounding.code} active - {payload.get('name')}"
    )


def audit_live(ontology: Ontology) -> list[Finding]:
    grounded = [g for g in ontology.groundings() if g.is_grounded]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return list(pool.map(lambda g: _verify_live(g, ontology), grounded))


# --- reporting ---------------------------------------------------------------

SYMBOL = {"ok": "  ok ", "warn": " warn", "fail": " FAIL"}


def report(title: str, findings: list[Finding]) -> int:
    print(f"\n{title}")
    print("-" * len(title))
    for finding in sorted(findings, key=lambda f: (f.level != "fail", f.local_id)):
        if finding.level == "ok":
            continue
        print(f"{SYMBOL[finding.level]}  {finding.local_id:<38} {finding.message}")

    failures = sum(1 for f in findings if f.failed)
    warnings = sum(1 for f in findings if f.level == "warn")
    passed = sum(1 for f in findings if f.level == "ok")
    print(f"\n  {passed} ok | {warnings} warnings | {failures} failures")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="resolve every code against the terminology server (needs network)",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args()

    ontology = get_ontology()
    groundings = ontology.groundings()
    mapped = [g for g in groundings if g.is_grounded]

    findings = audit_offline(ontology)
    live: list[Finding] = audit_live(ontology) if args.live else []

    if args.json:
        print(
            json.dumps(
                {
                    "mapping_set": ontology.mapping_set,
                    "mapped": len(mapped),
                    "unmapped": len(groundings) - len(mapped),
                    "offline": [f.__dict__ for f in findings],
                    "live": [f.__dict__ for f in live],
                },
                indent=2,
            )
        )
        return 1 if any(f.failed for f in [*findings, *live]) else 0

    print(f"mapping set  : v{ontology.mapping_set.get('version')} "
          f"(verified {ontology.mapping_set.get('verified_on')})")
    print(f"sources      : {', '.join(sorted(ontology.sources)) or 'none'}")
    print(f"concepts     : {len(mapped)} mapped | {len(groundings) - len(mapped)} unmapped")

    failures = report("Offline structural audit", findings)
    if args.live:
        failures += report("Live terminology audit", live)
    else:
        print("\n(run with --live to re-resolve every code against the terminology server)")

    print("\nRESULT:", "FAIL" if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
