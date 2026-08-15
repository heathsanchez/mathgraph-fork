from __future__ import annotations

import argparse
import json
from pathlib import Path

from bugsinpy_checkpoint3_qualify_v2 import (
    HARNESS_REVISION,
    PROTOCOL,
    UPSTREAM_COMMIT,
    attempt,
    run,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate one deterministic rank shard of the frozen pandas Checkpoint 3 candidate order."
    )
    ap.add_argument("--bugsinpy", type=Path, required=True)
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shard-index", type=int, required=True)
    ap.add_argument("--shard-count", type=int, required=True)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite evidence")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard index/count")

    head = run(["git", "rev-parse", "HEAD"], cwd=args.bugsinpy)["output"].strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"wrong BugsInPy commit: {head}")

    lock = json.loads(args.lock.read_text())
    if lock.get("commit") != UPSTREAM_COMMIT or lock.get("project_count") != 17:
        raise SystemExit("corpus lock invariant failed")
    projects = [p for p in lock["projects"] if p["project"] == "pandas"]
    if len(projects) != 1:
        raise SystemExit("pandas lock invariant failed")
    project = projects[0]

    candidates = [
        c for c in project["candidate_order"]
        if (int(c["rank"]) - 1) % args.shard_count == args.shard_index
    ]

    args.out.mkdir(parents=True)
    rows = []
    selected = []
    for candidate in candidates:
        row = attempt(args.bugsinpy, "pandas", candidate, args.timeout)
        row["split"] = project["split"]
        row["parallel_shard_index"] = args.shard_index
        row["parallel_shard_count"] = args.shard_count
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in (
            "project", "bug_id", "rank", "classification", "stage"
        )}), flush=True)
        if row["classification"] == "qualified":
            selected.append({key: row[key] for key in (
                "project", "split", "bug_id", "rank", "buggy_commit",
                "fixed_commit", "test_file", "repository"
            )})
            break

    summary = {
        "protocol": PROTOCOL,
        "harness_revision": HARNESS_REVISION,
        "upstream_commit": UPSTREAM_COMMIT,
        "split_requested": "all",
        "project": "pandas",
        "parallelization": "rank_modulo_only_execution_scheduling",
        "parallel_shard_index": args.shard_index,
        "parallel_shard_count": args.shard_count,
        "attempt_count": len(rows),
        "qualified_projects": 1 if selected else 0,
        "infrastructure_negatives": sum(r["classification"] != "qualified" for r in rows),
        "selected": selected,
    }
    (args.out / "QUALIFICATION_ATTEMPTS.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (args.out / "QUALIFIED_CORPUS.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
