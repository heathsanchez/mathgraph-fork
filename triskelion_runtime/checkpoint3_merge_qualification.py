from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

QUALIFICATION_PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_QUALIFICATION_V1"
UPSTREAM_COMMIT = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
MERGE_PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_QUALIFICATION_MERGE_V1"


def _project_order(lock: Mapping[str, Any]) -> list[str]:
    projects = lock.get("projects")
    if not isinstance(projects, list):
        raise ValueError("lock projects must be an array")
    order: list[str] = []
    for row in projects:
        if not isinstance(row, Mapping) or not isinstance(row.get("project"), str):
            raise ValueError("invalid project entry in lock")
        order.append(row["project"])
    if len(order) != len(set(order)):
        raise ValueError("duplicate project in lock")
    return order


def merge_qualification_evidence(
    sources: Sequence[tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]],
    *,
    lock: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    order = _project_order(lock)
    rank = {project: i for i, project in enumerate(order)}
    if lock.get("commit") != UPSTREAM_COMMIT:
        raise ValueError("lock upstream commit mismatch")

    selected_by_project: dict[str, dict[str, Any]] = {}
    evidence_projects: set[str] = set()
    attempts: list[dict[str, Any]] = []
    revisions: set[str] = set()

    for summary, source_attempts in sources:
        if summary.get("protocol") != QUALIFICATION_PROTOCOL:
            raise ValueError("qualification protocol mismatch")
        if summary.get("upstream_commit") != UPSTREAM_COMMIT:
            raise ValueError("qualification upstream commit mismatch")

        for revision in summary.get("harness_revisions", []):
            if revision:
                revisions.add(str(revision))
        revision = summary.get("harness_revision")
        if revision:
            revisions.add(str(revision))

        for row in source_attempts:
            if not isinstance(row, Mapping):
                raise ValueError("attempt rows must be objects")
            project = row.get("project")
            if project not in rank:
                raise ValueError(f"attempt references project outside frozen lock: {project}")
            evidence_projects.add(project)
            attempts.append(dict(row))

        selected = summary.get("selected", [])
        if not isinstance(selected, list):
            raise ValueError("selected must be an array")
        for raw in selected:
            if not isinstance(raw, Mapping):
                raise ValueError("selected rows must be objects")
            project = raw.get("project")
            if project not in rank:
                raise ValueError(f"selected project outside frozen lock: {project}")
            row = dict(raw)
            previous = selected_by_project.get(project)
            if previous is not None and previous != row:
                raise ValueError(f"conflicting selected evidence for project: {project}")
            selected_by_project[project] = row
            evidence_projects.add(project)

    attempts.sort(key=lambda row: (rank[row["project"]], int(row.get("rank", 10**9))))
    selected = [selected_by_project[p] for p in order if p in selected_by_project]
    missing_evidence = [p for p in order if p not in evidence_projects]

    result = {
        "protocol": QUALIFICATION_PROTOCOL,
        "merge_protocol": MERGE_PROTOCOL,
        "upstream_commit": UPSTREAM_COMMIT,
        "frozen_project_count": len(order),
        "projects_with_evidence": len(evidence_projects),
        "projects_missing_evidence": missing_evidence,
        "attempt_count": len(attempts),
        "qualified_projects": len(selected),
        "infrastructure_negatives": sum(
            row.get("classification") != "qualified" for row in attempts
        ),
        "harness_revisions": sorted(revisions),
        "selected": selected,
        "selection_order": "original frozen BUGSINPY_CORPUS_LOCK_V1 project order",
    }
    return result, attempts


def _load_source(path: Path) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
    summary_path = path / "QUALIFIED_CORPUS.json"
    attempts_path = path / "QUALIFICATION_ATTEMPTS.json"
    summary = json.loads(summary_path.read_text())
    attempts = json.loads(attempts_path.read_text())
    if not isinstance(summary, Mapping) or not isinstance(attempts, list):
        raise ValueError(f"invalid qualification source: {path}")
    return summary, attempts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", type=Path, required=True)
    ap.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).with_name("BUGSINPY_CORPUS_LOCK_V1.json"),
    )
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite merged qualification evidence")

    lock = json.loads(args.lock.read_text())
    if not isinstance(lock, Mapping):
        raise SystemExit("lock root must be an object")
    result, attempts = merge_qualification_evidence(
        [_load_source(path) for path in args.source], lock=lock
    )
    args.out.mkdir(parents=True)
    (args.out / "QUALIFIED_CORPUS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "QUALIFICATION_ATTEMPTS.json").write_text(
        json.dumps(attempts, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
