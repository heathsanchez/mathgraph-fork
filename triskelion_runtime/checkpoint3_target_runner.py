import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from triskelion_runtime.bugsinpy_checkpoint3_qualify_v2 import provision, relevant_tests


def run_git(repo, args, timeout=180):
    proc = subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return {
        "returncode": proc.returncode,
        "output": proc.stdout[-12000:],
    }


def load_bundle_case(bundle, case_index):
    manifest = json.loads((bundle / "MANIFEST.json").read_text())
    records = manifest.get("records", [])
    matches = [row for row in records if row.get("case_index") == case_index]
    if len(matches) != 1:
        raise RuntimeError("protected test bundle case mismatch")
    return matches[0]


def restore_pristine(repo, buggy_commit, bundle, case_index):
    reset = run_git(repo, ["reset", "--hard", buggy_commit])
    if reset["returncode"] != 0:
        return {"ok": False, "stage": "reset", "detail": reset}
    case = load_bundle_case(bundle, case_index)
    restored = []
    for row in case.get("files", []):
        source = bundle / row["bundle_path"]
        payload = source.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != row["sha256"]:
            return {
                "ok": False,
                "stage": "test_bundle_hash",
                "path": row["relative_path"],
            }
        target = repo / row["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        restored.append(row["relative_path"])
    return {"ok": True, "stage": "complete", "restored_tests": restored}


def apply_patch(repo, patch_path, timeout=180):
    check = subprocess.run(
        ["git", "apply", "--check", str(patch_path)],
        cwd=str(repo),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if check.returncode != 0:
        return {
            "ok": False,
            "stage": "patch_check",
            "returncode": check.returncode,
            "output": check.stdout[-12000:],
        }
    applied = subprocess.run(
        ["git", "apply", str(patch_path)],
        cwd=str(repo),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return {
        "ok": applied.returncode == 0,
        "stage": "patch_apply",
        "returncode": applied.returncode,
        "output": applied.stdout[-12000:],
    }


def prepare(repo, buggy_commit, bug_dir, bundle, case_index, timeout):
    pristine = restore_pristine(repo, buggy_commit, bundle, case_index)
    if not pristine["ok"]:
        return {"ok": False, "stage": pristine["stage"], "pristine": pristine}
    provision_result = provision(repo, bug_dir, timeout)
    if not provision_result.get("ok"):
        return {
            "ok": False,
            "stage": "provision",
            "provision": provision_result,
        }
    baseline = relevant_tests(repo, bug_dir, timeout)
    if not baseline.get("ok"):
        return {"ok": False, "stage": "baseline_harness", "baseline": baseline}
    if baseline.get("test_passed"):
        return {
            "ok": False,
            "stage": "baseline_unreproduced",
            "baseline": baseline,
        }
    return {
        "ok": True,
        "stage": "complete",
        "pristine": pristine,
        "provision": provision_result,
        "baseline": baseline,
    }


def evaluate(repo, buggy_commit, bug_dir, bundle, case_index, patch_path, timeout):
    pristine = restore_pristine(repo, buggy_commit, bundle, case_index)
    if not pristine["ok"]:
        return {
            "ok": False,
            "classification": "infrastructure_error",
            "stage": pristine["stage"],
            "pristine": pristine,
        }
    patch = apply_patch(repo, patch_path, timeout=min(timeout, 180))
    if not patch["ok"]:
        return {
            "ok": True,
            "classification": "competence",
            "stage": patch["stage"],
            "patch_applied": False,
            "test_executed": False,
            "repaired": False,
            "patch": patch,
        }
    test = relevant_tests(repo, bug_dir, timeout)
    if not test.get("ok"):
        return {
            "ok": False,
            "classification": "infrastructure_error",
            "stage": "test_harness",
            "patch_applied": True,
            "test": test,
        }
    return {
        "ok": True,
        "classification": "competence",
        "stage": "complete",
        "patch_applied": True,
        "test_executed": True,
        "repaired": bool(test.get("test_passed")),
        "test": test,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "evaluate"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--buggy-commit", required=True)
    parser.add_argument("--bug-dir", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--case-index", type=int, required=True)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    if args.mode == "prepare":
        result = prepare(
            args.repo,
            args.buggy_commit,
            args.bug_dir,
            args.bundle,
            args.case_index,
            args.timeout,
        )
    else:
        if args.patch is None:
            raise SystemExit("--patch is required for evaluate mode")
        result = evaluate(
            args.repo,
            args.buggy_commit,
            args.bug_dir,
            args.bundle,
            args.case_index,
            args.patch,
            args.timeout,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
