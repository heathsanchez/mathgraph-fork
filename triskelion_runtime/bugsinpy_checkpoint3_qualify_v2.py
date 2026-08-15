import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional


UPSTREAM_COMMIT = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_QUALIFICATION_V1"
HARNESS_REVISION = "V2_1_EXACT_COMMITS_FIXED_REGRESSION_TEST_ENCODING_AWARE"


def run(cmd, cwd=None, env=None,
        timeout: int = 600) -> dict:
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, universal_newlines=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "duration_s": round(time.perf_counter() - started, 3),
            "output": proc.stdout[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return {
            "cmd": cmd,
            "returncode": None,
            "timeout": True,
            "duration_s": round(time.perf_counter() - started, 3),
            "output": output[-12000:],
        }


def parse_assignments(path: Path) -> Dict[str, str]:
    values = {}  # type: Dict[str, str]
    for line in path.read_text().splitlines():
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=["\'](.*)["\']\s*$', line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    return values


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_metadata(bug_dir: Path, locked: dict) -> None:
    for name, expected in locked.get("metadata_sha256", {}).items():
        path = bug_dir / name
        if not path.exists() or sha256(path) != expected:
            raise RuntimeError(f"metadata lock mismatch: {bug_dir}/{name}")


def runtime_env(repo: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["VIRTUAL_ENV"] = str(repo / "env")
    env["PATH"] = str(repo / "env" / "bin") + os.pathsep + env.get("PATH", "")
    return env


def read_benchmark_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def shell_lines(path: Path) -> List[str]:
    return [line.strip().replace("\r", "") for line in read_benchmark_text(path).splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def clone_at(url: str, commit: str, repo: Path, timeout: int) -> dict:
    clone = run(["git", "clone", "--quiet", "--no-checkout", url, str(repo)], timeout=timeout)
    if clone["returncode"] != 0:
        return {"ok": False, "stage": "clone", "detail": clone}
    fetch = run(["git", "fetch", "--quiet", "origin", commit], cwd=repo, timeout=timeout)
    if fetch["returncode"] != 0:
        return {"ok": False, "stage": "fetch", "detail": fetch}
    checkout = run(["git", "checkout", "--quiet", "--detach", commit], cwd=repo, timeout=timeout)
    head = run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=timeout)
    ok = checkout["returncode"] == 0 and head["returncode"] == 0 and head["output"].strip() == commit
    return {"ok": ok, "stage": "checkout", "clone": clone, "fetch": fetch,
            "checkout": checkout, "head": head}


def provision(repo: Path, bug_dir: Path, timeout: int) -> dict:
    steps = []  # type: List[dict]
    create = run([sys.executable, "-m", "venv", "env"], cwd=repo, timeout=timeout)
    steps.append({"stage": "venv", **create})
    if create["returncode"] != 0:
        return {"ok": False, "stage": "venv", "steps": steps}
    env = runtime_env(repo)
    requirements = bug_dir / "requirements.txt"
    setup = bug_dir / "setup.sh"
    requirement_lines = shell_lines(requirements) if requirements.exists() else []
    setup_lines = shell_lines(setup) if setup.exists() else []
    # The upstream compiler installs requirements both before and after setup. Preserve that
    # behavior, but retain each subprocess verdict instead of accepting its unconditional flag.
    for pass_number in (1, 2):
        if pass_number == 2:
            for command in setup_lines:
                result = run(["bash", "-c", command], cwd=repo, env=env, timeout=timeout)
                steps.append({"stage": "setup", "command": command, **result})
                if result["returncode"] != 0:
                    return {"ok": False, "stage": "setup", "steps": steps}
        for requirement in requirement_lines:
            command = f"python -m pip install {requirement}"
            result = run(["bash", "-c", command], cwd=repo, env=env, timeout=timeout)
            steps.append({"stage": f"requirements_{pass_number}", "requirement": requirement,
                          **result})
            if result["returncode"] != 0:
                return {"ok": False, "stage": f"requirements_{pass_number}", "steps": steps}
    return {"ok": True, "stage": "complete", "steps": steps}


def relevant_tests(repo: Path, bug_dir: Path, timeout: int) -> dict:
    script = bug_dir / "run_test.sh"
    if not script.exists():
        return {"ok": False, "stage": "missing_test_script", "steps": []}
    env = runtime_env(repo)
    steps = []  # type: List[dict]
    for command in shell_lines(script):
        result = run(["bash", "-c", command], cwd=repo, env=env, timeout=timeout)
        steps.append({"stage": "test", "command": command, **result})
    passed = bool(steps) and all(step["returncode"] == 0 for step in steps)
    return {"ok": True, "stage": "test", "test_passed": passed, "steps": steps}


def evaluate_version(url: str, expected_commit: str, repo: Path, bug_dir: Path,
                     test_files: List[str], timeout: int, fixed_repo: Optional[Path] = None) -> dict:
    checkout = clone_at(url, expected_commit, repo, timeout)
    if not checkout["ok"]:
        return {"ok": False, "stage": checkout["stage"], "checkout": checkout}
    copied_tests = []  # type: List[str]
    if fixed_repo is not None:
        for relative in test_files:
            source = fixed_repo / relative
            target = repo / relative
            if not source.is_file():
                return {"ok": False, "stage": "fixed_regression_test_missing",
                        "test_file": relative, "checkout": checkout}
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_tests.append(relative)
    provision_result = provision(repo, bug_dir, timeout)
    if not provision_result["ok"]:
        return {"ok": False, "stage": "provision", "provision": provision_result}
    test_result = relevant_tests(repo, bug_dir, timeout)
    if not test_result["ok"]:
        return {"ok": False, "stage": "test_harness", "provision": provision_result,
                "test": test_result}
    return {"ok": True, "stage": "complete", "checkout": checkout,
            "fixed_regression_tests_copied": copied_tests, "provision": provision_result,
            "test": test_result}


def attempt(bugsinpy: Path, project: str, candidate: dict, timeout: int) -> dict:
    bug_id = candidate["bug_id"]
    bug_dir = bugsinpy / "projects" / project / "bugs" / bug_id
    verify_metadata(bug_dir, candidate)
    info = parse_assignments(bug_dir / "bug.info")
    pinfo = parse_assignments(bugsinpy / "projects" / project / "project.info")
    row = {
        "project": project,
        "bug_id": bug_id,
        "rank": candidate["rank"],
        "python_version_declared": info.get("python_version"),
        "python_version_executed": ".".join(map(str, sys.version_info[:3])),
        "test_file": info.get("test_file", ""),
        "buggy_commit": info.get("buggy_commit_id"),
        "fixed_commit": info.get("fixed_commit_id"),
        "repository": pinfo.get("github_url"),
    }
    if not all((row["repository"], row["buggy_commit"], row["fixed_commit"], row["test_file"],
                row["python_version_declared"])):
        return {**row, "classification": "infrastructure_negative", "stage": "metadata"}
    declared_major_minor = ".".join(row["python_version_declared"].split(".")[:2])
    executed_major_minor = ".".join(row["python_version_executed"].split(".")[:2])
    if executed_major_minor != declared_major_minor:
        return {**row, "classification": "infrastructure_negative", "stage": "python_version_mismatch"}
    test_files = [item for item in row["test_file"].split(";") if item]
    with tempfile.TemporaryDirectory(prefix="triskelion_bip_q_") as temp_dir:
        root = Path(temp_dir)
        fixed_repo = root / "fixed"
        fixed = evaluate_version(row["repository"], row["fixed_commit"], fixed_repo, bug_dir,
                                 test_files, timeout)
        if not fixed["ok"] or not fixed.get("test", {}).get("test_passed"):
            return {**row, "classification": "infrastructure_negative", "stage": "fixed_test",
                    "fixed": fixed}
        buggy = evaluate_version(row["repository"], row["buggy_commit"], root / "buggy", bug_dir,
                                 test_files, timeout, fixed_repo=fixed_repo)
        if not buggy["ok"]:
            return {**row, "classification": "infrastructure_negative", "stage": "buggy_provision",
                    "fixed": fixed, "buggy": buggy}
        if buggy.get("test", {}).get("test_passed"):
            return {**row, "classification": "infrastructure_negative", "stage": "buggy_unreproduced",
                    "fixed": fixed, "buggy": buggy}
        return {**row, "classification": "qualified", "stage": "complete",
                "fixed": fixed, "buggy": buggy}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bugsinpy", type=Path, required=True)
    parser.add_argument("--lock", type=Path,
                        default=Path(__file__).with_name("BUGSINPY_CORPUS_LOCK_V1.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split", choices=("acquisition", "protected", "all"), default="all")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-candidates-per-project", type=int, default=0)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen evidence")
    head = run(["git", "rev-parse", "HEAD"], cwd=args.bugsinpy)["output"].strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"wrong BugsInPy commit: {head}")
    lock = json.loads(args.lock.read_text())
    if lock["commit"] != UPSTREAM_COMMIT or lock["project_count"] != 17:
        raise SystemExit("corpus lock invariant failed")
    args.out.mkdir(parents=True)
    rows = []  # type: List[dict]
    selected = []  # type: List[dict]
    for project in lock["projects"]:
        if args.split != "all" and project["split"] != args.split:
            continue
        candidates = project["candidate_order"]
        if args.max_candidates_per_project:
            candidates = candidates[:args.max_candidates_per_project]
        winner = None
        for candidate in candidates:
            row = attempt(args.bugsinpy, project["project"], candidate, args.timeout)
            row["split"] = project["split"]
            rows.append(row)
            print(json.dumps({key: row.get(key) for key in
                              ("project", "bug_id", "split", "classification", "stage")}),
                  flush=True)
            if row["classification"] == "qualified":
                winner = row
                selected.append({key: row[key] for key in
                                 ("project", "split", "bug_id", "rank", "buggy_commit",
                                  "fixed_commit", "test_file", "repository")})
                break
        if winner is None:
            print(f"NO QUALIFIED BUG: {project['project']}", flush=True)
    summary = {
        "protocol": PROTOCOL,
        "harness_revision": HARNESS_REVISION,
        "upstream_commit": UPSTREAM_COMMIT,
        "split_requested": args.split,
        "projects_attempted": len({row["project"] for row in rows}),
        "attempt_count": len(rows),
        "qualified_projects": len(selected),
        "infrastructure_negatives": sum(row["classification"] != "qualified" for row in rows),
        "selected": selected,
    }
    (args.out / "QUALIFICATION_ATTEMPTS.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (args.out / "QUALIFIED_CORPUS.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
