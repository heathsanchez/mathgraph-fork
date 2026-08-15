from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from triskelion_runtime.bugsinpy_checkpoint3_qualify_v2 import (
    UPSTREAM_COMMIT,
    attempt,
    parse_assignments,
    run,
)

PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT4_FRESH_QUALIFICATION_V1"


def project_entry(lock: Mapping[str, Any], project: str) -> Mapping[str, Any]:
    rows = [p for p in lock.get("projects", []) if p.get("project") == project]
    if len(rows) != 1:
        raise SystemExit(f"expected one frozen project entry for {project}; got {len(rows)}")
    return rows[0]


def selected_candidates(*, bugsinpy: Path, lock: Mapping[str, Any], prior: list[Mapping[str, Any]], project: str, python_minor: str):
    attempted = {(str(r.get("project")), str(r.get("bug_id"))) for r in prior if isinstance(r, Mapping)}
    selected = []
    for frozen_index, candidate in enumerate(project_entry(lock, project).get("candidate_order", [])):
        bug_id = str(candidate.get("bug_id"))
        if (project, bug_id) in attempted:
            continue
        info = parse_assignments(bugsinpy / "projects" / project / "bugs" / bug_id / "bug.info")
        declared = str(info.get("python_version") or "")
        if ".".join(declared.split(".")[:2]) != python_minor:
            continue
        selected.append((frozen_index, candidate))
    return selected


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bugsinpy", type=Path, required=True)
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--prior-attempts", type=Path, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--python-minor", choices=("3.6", "3.7", "3.8"), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()

    head = run(["git", "rev-parse", "HEAD"], cwd=args.bugsinpy)["output"].strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"wrong BugsInPy commit: {head}")
    lock = json.loads(args.lock.read_text())
    prior = json.loads(args.prior_attempts.read_text())
    if lock.get("commit") != UPSTREAM_COMMIT or not isinstance(prior, list) or len(prior) != 351:
        raise SystemExit("frozen prior/lock invariant failed")

    selected = selected_candidates(
        bugsinpy=args.bugsinpy, lock=lock, prior=prior,
        project=args.project, python_minor=args.python_minor,
    )
    plan = {
        "protocol": PROTOCOL,
        "project": args.project,
        "python_minor": args.python_minor,
        "candidate_count": len(selected),
        "candidates": [
            {"frozen_project_index": i, "bug_id": str(c.get("bug_id")), "rank": c.get("rank")}
            for i, c in selected
        ],
    }
    if args.plan_only:
        print(json.dumps(plan, sort_keys=True))
        return
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite fresh qualification evidence")
    args.out.mkdir(parents=True)
    rows = []
    for frozen_index, candidate in selected:
        row = attempt(args.bugsinpy, args.project, candidate, args.timeout)
        row["cp4_frozen_project_index"] = frozen_index
        rows.append(row)
    summary = {
        **plan,
        "attempt_count": len(rows),
        "qualified_count": sum(r.get("classification") == "qualified" for r in rows),
        "infrastructure_negative_count": sum(r.get("classification") == "infrastructure_negative" for r in rows),
        "python_executed": ".".join(map(str, sys.version_info[:3])),
    }
    (args.out / "ATTEMPTS.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (args.out / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
