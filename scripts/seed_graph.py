#!/usr/bin/env python
"""Seed Neo4j from a clean state.

    python scripts/seed_graph.py            # wipe + seed, then verify
    python scripts/seed_graph.py --no-wipe  # merge into an existing database
    python scripts/seed_graph.py --dry-run  # build the projection only

The verification step asserts the counts the assessment specifies (50 exercises,
19 muscle groups, 9 joints, 36 movement patterns, 32 equipment types) so a
mis-seeded graph fails loudly instead of quietly under-filtering later.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.graph.bootstrap import verify  # noqa: E402
from app.graph.memory_repository import InMemoryGraphRepository  # noqa: E402
from app.ontology.loader import get_ontology  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the knowledge graph")
    parser.add_argument("--no-wipe", action="store_true", help="do not clear the database first")
    parser.add_argument("--dry-run", action="store_true", help="build in memory, do not write")
    args = parser.parse_args()

    settings = get_settings()
    ontology = get_ontology()

    print(f"exercises      : {settings.exercises_path}")
    print(f"member context : {settings.member_context_path}")

    if args.dry_run or settings.graph_backend == "memory":
        repository = InMemoryGraphRepository.from_files(
            settings.exercises_path, settings.member_context_path, ontology
        )
        stats = repository.stats()
        mode = "dry-run (in-memory projection)"
    else:
        from app.graph.neo4j_repository import Neo4jGraphRepository

        print(f"neo4j          : {settings.neo4j_uri}")
        repository = Neo4jGraphRepository.connect(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            settings.neo4j_database,
            settings.exercises_path,
            settings.member_context_path,
            ontology,
        )
        stats = repository.seed(wipe=not args.no_wipe)
        repository.close()
        mode = "neo4j"

    print(f"\nseeded via {mode}\n")
    for key, value in sorted(stats.items()):
        print(f"  {key:38s} {value}")

    problems = verify(stats, settings.exercises_path)
    if problems:
        print("\nVERIFICATION FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nVerification passed: 50 exercises, 19 muscles, 36 patterns, 32 equipment,")
    print("all 9 catalog joints mapped, anatomy + contraindication edges present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
