from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

UPSTREAM_COMMIT = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_QUALIFICATION_V1"


def run(cmd, *, cwd=None, env=None, timeout=600, check=False):
    started = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        row = {"cmd": cmd, "returncode": p.returncode,
               "duration_s": round(time.perf_counter() - started, 3),
               "output": p.stdout[-12000:]}
        if check and p.returncode:
            raise RuntimeError(json.dumps(row))
        return row
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return {"cmd": cmd, "returncode": None, "timeout": True,
                "duration_s": round(time.perf_counter() - started, 3), "output": out[-12000:]}


def parse_assignments(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=["\'](.*)["\']\s*$', line.strip())
        if m:
            values[m.group(1)] = m.group(2)
    return values


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_metadata(bug_dir: Path, locked: dict) -> None:
    for name, expected in locked.get("metadata_sha256", {}).items():
        path = bug_dir / name
        if not path.exists() or sha256(path) != expected:
            raise RuntimeError(f"metadata lock mismatch: {bug_dir}/{name}")


def clone_at(url: str, commit: str, dst: Path, timeout: int) -> dict:
    clone = run(["git", "clone", "--quiet", "--no-checkout", url, str(dst)], timeout=timeout)
    if clone["returncode"] != 0:
        return {"ok": False, "stage": "clone", "detail": clone}
    fetch = run(["git", "fetch", "--quiet", "origin", commit], cwd=dst, timeout=timeout)
    if fetch["returncode"] != 0:
        return {"ok": False, "stage": "fetch", "detail": fetch}
    checkout = run(["git", "checkout", "--quiet", "--detach", commit], cwd=dst, timeout=timeout)
    return {"ok": checkout["returncode"] == 0, "stage": "checkout", "detail": checkout}


def provision_and_test(repo: Path, bug_dir: Path, test_file: str, timeout: int) -> dict:
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    steps = []
    setup = bug_dir / "setup.sh"
    req = bug_dir / "requirements.txt"
    if setup.exists():
        s = run(["bash", str(setup)], cwd=repo, env=env, timeout=timeout)
        steps.append({"stage": "setup", **s})
        if s["returncode"] != 0:
            return {"ok": False, "stage": "setup", "steps": steps}
    if req.exists() and req.read_text().strip():
        r = run(["python", "-m", "pip", "install", "-r", str(req)], cwd=repo, env=env, timeout=timeout)
        steps.append({"stage": "requirements", **r})
        if r["returncode"] != 0:
            return {"ok": False, "stage": "requirements", "steps": steps}
    script = bug_dir / "run_test.sh"
    cmd = ["bash", str(script)] if script.exists() else ["python", "-m", "pytest", "-q", test_file]
    t = run(cmd, cwd=repo, env=env, timeout=timeout)
    steps.append({"stage": "test", **t})
    return {"ok": True, "stage": "test", "test_passed": t["returncode"] == 0, "steps": steps}


def attempt(bugsinpy: Path, project: str, candidate: dict, timeout: int) -> dict:
    bug_id = candidate["bug_id"]
    bug_dir = bugsinpy / "projects" / project / "bugs" / bug_id
    verify_metadata(bug_dir, candidate)
    info = parse_assignments(bug_dir / "bug.info")
    pinfo = parse_assignments(bugsinpy / "projects" / project / "project.info")
    url = pinfo.get("github_url")
    buggy = info.get("buggy_commit_id")
    fixed = info.get("fixed_commit_id")
    test_file = info.get("test_file", "")
    row = {"project": project, "bug_id": bug_id, "rank": candidate["rank"],
           "python_version_declared": info.get("python_version"), "test_file": test_file,
           "buggy_commit": buggy, "fixed_commit": fixed, "repository": url}
    if not all((url, buggy, fixed, test_file)):
        return {**row, "classification": "infrastructure_negative", "stage": "metadata"}
    with tempfile.TemporaryDirectory(prefix="triskelion_bip_q_") as td:
        root = Path(td)
        fixed_repo = root / "fixed"
        c = clone_at(url, fixed, fixed_repo, timeout)
        if not c["ok"]:
            return {**row, "classification": "infrastructure_negative", "stage": f"fixed_{c['stage']}", "detail": c}
        fixed_result = provision_and_test(fixed_repo, bug_dir, test_file, timeout)
        if not fixed_result["ok"] or not fixed_result.get("test_passed"):
            return {**row, "classification": "infrastructure_negative", "stage": "fixed_test", "fixed": fixed_result}
        buggy_repo = root / "buggy"
        c = clone_at(url, buggy, buggy_repo, timeout)
        if not c["ok"]:
            return {**row, "classification": "infrastructure_negative", "stage": f"buggy_{c['stage']}", "detail": c}
        buggy_result = provision_and_test(buggy_repo, bug_dir, test_file, timeout)
        if not buggy_result["ok"]:
            return {**row, "classification": "infrastructure_negative", "stage": "buggy_provision", "buggy": buggy_result}
        if buggy_result.get("test_passed"):
            return {**row, "classification": "infrastructure_negative", "stage": "buggy_unreproduced",
                    "fixed": fixed_result, "buggy": buggy_result}
        return {**row, "classification": "qualified", "stage": "complete",
                "fixed": fixed_result, "buggy": buggy_result}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bugsinpy", type=Path, required=True)
    ap.add_argument("--lock", type=Path, default=Path(__file__).with_name("BUGSINPY_CORPUS_LOCK_V1.json"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", choices=("acquisition", "protected", "all"), default="all")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-candidates-per-project", type=int, default=0,
                    help="0 means exhaust frozen candidate order until qualification")
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen evidence")
    head = run(["git", "rev-parse", "HEAD"], cwd=args.bugsinpy, check=True)["output"].strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"wrong BugsInPy commit: {head}")
    lock = json.loads(args.lock.read_text())
    if lock["commit"] != UPSTREAM_COMMIT or lock["project_count"] != 17:
        raise SystemExit("corpus lock invariant failed")
    args.out.mkdir(parents=True)
    rows, selected = [], []
    for p in lock["projects"]:
        if args.split != "all" and p["split"] != args.split:
            continue
        attempts = p["candidate_order"]
        if args.max_candidates_per_project:
            attempts = attempts[:args.max_candidates_per_project]
        winner = None
        for candidate in attempts:
            row = attempt(args.bugsinpy, p["project"], candidate, args.timeout)
            row["split"] = p["split"]
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("project", "bug_id", "split", "classification", "stage")}), flush=True)
            if row["classification"] == "qualified":
                winner = row
                selected.append({"project": p["project"], "split": p["split"], "bug_id": row["bug_id"],
                                 "rank": row["rank"], "buggy_commit": row["buggy_commit"],
                                 "fixed_commit": row["fixed_commit"], "test_file": row["test_file"],
                                 "repository": row["repository"]})
                break
        if winner is None:
            print(f"NO QUALIFIED BUG: {p['project']}", flush=True)
    summary = {"protocol": PROTOCOL, "upstream_commit": UPSTREAM_COMMIT,
               "split_requested": args.split, "projects_attempted": len({r['project'] for r in rows}),
               "attempt_count": len(rows), "qualified_projects": len(selected),
               "infrastructure_negatives": sum(r["classification"] != "qualified" for r in rows),
               "selected": selected}
    (args.out / "QUALIFICATION_ATTEMPTS.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (args.out / "QUALIFIED_CORPUS.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
