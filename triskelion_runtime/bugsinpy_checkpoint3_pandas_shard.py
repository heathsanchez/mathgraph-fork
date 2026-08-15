from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# When executed as a file, Python puts triskelion_runtime/ rather than the repo root
# on sys.path. Add the repo root explicitly so the package import is deterministic in CI.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from triskelion_runtime.bugsinpy_checkpoint3_qualify_v2 import (
    HARNESS_REVISION,
    PROTOCOL,
    UPSTREAM_COMMIT,
    attempt,
    run,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate one deterministic position shard of the frozen pandas Checkpoint 3 candidate order."
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

    # IMPORTANT: candidate['rank'] is the frozen hash-based rank key, not an integer.
    # The scientific sequential order is the list position in candidate_order. Shard only
    # by that immutable position. The reducer later chooses the minimum successful position
    # and retains exactly the sequential prefix that would have been observed without parallelism.
    candidates = [
        (position, candidate)
        for position, candidate in enumerate(project["candidate_order"], start=1)
        if (position - 1) % args.shard_count == args.shard_index
    ]

    args.out.mkdir(parents=True)
    rows = []
    selected = []
    for position, candidate in candidates:
        row = attempt(args.bugsinpy, "pandas", candidate, args.timeout)
        row["split"] = project["split"]
        row["frozen_order_index"] = position
        row["parallel_shard_index"] = args.shard_index
        row["parallel_shard_count"] = args.shard_count
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in (
            "project", "bug_id", "rank", "frozen_order_index", "classification", "stage"
        )}), flush=True)
        if row["classification"] == "qualified":
            item = {key: row[key] for key in (
                "project", "split", "bug_id", "rank", "buggy_commit",
                "fixed_commit", "test_file", "repository"
            )}
            item["frozen_order_index"] = position
            selected.append(item)
            break

    summary = {
        "protocol": PROTOCOL,
        "harness_revision": HARNESS_REVISION,
        "upstream_commit": UPSTREAM_COMMIT,
        "split_requested": "all",
        "project": "pandas",
        "parallelization": "frozen_candidate_order_position_modulo_only",
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
