from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

UPSTREAM_COMMIT = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
SEED = 20260819


def rank(label: str) -> str:
    return hashlib.sha256(f"{SEED}:{label}".encode()).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists(): raise SystemExit("output exists; refusing to overwrite")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.repo, text=True).strip()
    if head != UPSTREAM_COMMIT: raise SystemExit(f"wrong BugsInPy commit: {head}")
    projects = []
    for project_dir in (args.repo / "projects").iterdir():
        if not project_dir.is_dir(): continue
        candidates = []
        for bug_dir in (project_dir / "bugs").iterdir():
            if not bug_dir.is_dir() or not (bug_dir / "bug.info").exists(): continue
            files = {}
            for name in ("bug.info", "requirements.txt", "run_test.sh", "setup.sh", "bug_patch.txt"):
                path = bug_dir / name
                if path.exists(): files[name] = digest(path)
            candidates.append({"bug_id": bug_dir.name, "rank": rank(f"bug:{project_dir.name}:{bug_dir.name}"), "metadata_sha256": files})
        candidates.sort(key=lambda x: (x["rank"], x["bug_id"]))
        projects.append({"project": project_dir.name, "rank": rank(f"project:{project_dir.name}"), "candidate_order": candidates})
    projects.sort(key=lambda x: x["rank"])
    for i, item in enumerate(projects): item["split"] = "acquisition" if i < 5 else "protected"
    lock = {
        "protocol": "TRISKELION_BUGSINPY_CORPUS_LOCK_V1", "seed": SEED,
        "upstream": "soarsmu/BugsInPy", "commit": UPSTREAM_COMMIT,
        "project_count": len(projects), "bug_count": sum(len(x["candidate_order"]) for x in projects),
        "selection": "hash-order projects; first five are acquisition; remaining projects protected; within each project choose first infrastructure-qualified bug in frozen hash order",
        "qualification": "without source inspection: checkout exact commits, provision in disposable environment, fixed relevant tests pass, buggy relevant tests fail; retain every attempted infrastructure negative",
        "projects": projects,
    }
    args.out.mkdir(parents=True)
    text = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    (args.out / "CORPUS_LOCK.json").write_text(text)
    (args.out / "CORPUS_LOCK.sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "\n")
    print(json.dumps({"project_count": lock["project_count"], "bug_count": lock["bug_count"],
                      "acquisition_projects": [x["project"] for x in projects[:5]],
                      "protected_projects": [x["project"] for x in projects[5:]],
                      "sha256": hashlib.sha256(text.encode()).hexdigest()}, indent=2))


if __name__ == "__main__": main()
