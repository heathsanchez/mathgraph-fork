from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from triskelion_runtime.checkpoint3_build_capability import truncate_head_tail
from triskelion_runtime.checkpoint3_causal_results import (
    summarize_four_arm_results,
    validate_complete_four_arm_results,
)
from triskelion_runtime.checkpoint3_eval_core import (
    ARMS,
    arm_context,
    extract_unified_diff,
    misapplication,
    parse_file_selection,
    rule_from_public,
    safe_repo_path,
    validate_patch_safety,
)

EVAL_PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_PROTECTED_EVAL_V1"
OMISSION = "\n... [FROZEN EVIDENCE TRUNCATION] ...\n"


def run(cmd: Sequence[str], *, cwd: Path | None = None, timeout: int = 900) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            list(cmd), cwd=str(cwd) if cwd else None, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
        return {"returncode": proc.returncode, "output": proc.stdout[-24000:]}
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return {"returncode": None, "timeout": True, "output": output[-24000:]}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def clone_buggy(repository: str, buggy_commit: str, destination: Path, timeout: int = 300) -> dict[str, Any]:
    clone = run(["git", "clone", "--quiet", "--no-checkout", repository, str(destination)], timeout=timeout)
    if clone["returncode"] != 0:
        return {"ok": False, "stage": "clone", "detail": clone}
    fetch = run(["git", "fetch", "--quiet", "origin", buggy_commit], cwd=destination, timeout=timeout)
    if fetch["returncode"] != 0:
        return {"ok": False, "stage": "fetch", "detail": fetch}
    checkout = run(["git", "checkout", "--quiet", "--detach", buggy_commit], cwd=destination, timeout=timeout)
    head = run(["git", "rev-parse", "HEAD"], cwd=destination, timeout=timeout)
    ok = checkout["returncode"] == 0 and head["returncode"] == 0 and head["output"].strip() == buggy_commit
    return {"ok": ok, "stage": "checkout", "checkout": checkout, "head": head}


def repository_tree(repo: Path) -> str:
    result = run(["git", "ls-files"], cwd=repo, timeout=120)
    if result["returncode"] != 0:
        raise RuntimeError("git ls-files failed")
    return "\n".join(sorted(line for line in result["output"].splitlines() if line.strip()))


def bundle_record(bundle: Path, case_index: int) -> Mapping[str, Any]:
    manifest = load_json(bundle / "MANIFEST.json")
    matches = [row for row in manifest.get("records", []) if row.get("case_index") == case_index]
    if len(matches) != 1:
        raise ValueError(f"protected test bundle missing case index {case_index}")
    return matches[0]


def protected_test_text(bundle: Path, case_index: int) -> tuple[str, tuple[str, ...]]:
    record = bundle_record(bundle, case_index)
    chunks: list[str] = []
    paths: list[str] = []
    for row in record.get("files", []):
        path = safe_repo_path(str(row["relative_path"]))
        payload = (bundle / row["bundle_path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError("protected test bundle hash mismatch")
        paths.append(path)
        chunks.append(f"### {path}\n{payload.decode('utf-8', errors='replace')}")
    return "\n\n".join(chunks), tuple(paths)


def baseline_failure_text(prepare_result: Mapping[str, Any]) -> str:
    baseline = prepare_result.get("baseline")
    steps = baseline.get("steps") if isinstance(baseline, Mapping) else None
    if not isinstance(steps, list) or not steps:
        raise ValueError("prepared baseline missing regression steps")
    chunks: list[str] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        if step.get("command"):
            chunks.append(f"$ {step['command']}")
        if step.get("output"):
            chunks.append(str(step["output"]))
        chunks.append(f"[returncode={step.get('returncode')}]")
    return "\n".join(chunks)


def docker_image_for(version: str, images: Mapping[str, str]) -> str:
    major_minor = ".".join(version.split(".")[:2])
    if major_minor not in images:
        raise ValueError(f"unsupported frozen Python version: {version}")
    return images[major_minor]


def container_path(host_path: Path, workspace: Path) -> str:
    resolved = host_path.resolve()
    relative = resolved.relative_to(workspace.resolve())
    return "/work/" + str(relative).replace(os.sep, "/")


def target_call(
    *,
    image: str,
    mode: str,
    repo: Path,
    buggy_commit: str,
    bug_dir: Path,
    bundle: Path,
    case_index: int,
    workspace: Path,
    patch: Path | None = None,
    timeout: int = 1200,
) -> tuple[bool, Mapping[str, Any], str]:
    args = [
        "docker", "run", "--rm", "-v", f"{workspace.resolve()}:/work", "-w", "/work",
        image, "python", "triskelion_runtime/checkpoint3_target_runner.py", mode,
        "--repo", container_path(repo, workspace),
        "--buggy-commit", buggy_commit,
        "--bug-dir", container_path(bug_dir, workspace),
        "--bundle", container_path(bundle, workspace),
        "--case-index", str(case_index),
        "--timeout", str(timeout),
    ]
    if patch is not None:
        args.extend(["--patch", container_path(patch, workspace)])
    result = run(args, cwd=workspace, timeout=timeout + 120)
    text = result.get("output", "")
    parsed: Mapping[str, Any] = {}
    try:
        parsed_value = json.loads(text)
        if isinstance(parsed_value, Mapping):
            parsed = parsed_value
    except Exception:
        pass
    return result.get("returncode") == 0, parsed, text


def raw_memory_context(raw_memory: Sequence[Mapping[str, Any]], limit: int) -> str:
    text = json.dumps(list(raw_memory), indent=2, sort_keys=True)
    return truncate_head_tail(text, limit)


def selected_source_text(repo: Path, paths: Sequence[str], *, test_paths: Sequence[str], limit: int) -> str:
    tests = {safe_repo_path(path) for path in test_paths}
    chunks: list[str] = []
    for raw in paths:
        path = safe_repo_path(raw)
        if path in tests:
            raise ValueError("model selected protected test as production source")
        source = repo / path
        if not source.is_file():
            raise ValueError(f"selected source does not exist: {path}")
        chunks.append(f"### {path}\n{source.read_text(encoding='utf-8', errors='replace')}")
    return truncate_head_tail("\n\n".join(chunks), limit)


def call1_prompt(*, tree: str, failure: str, tests: str, context: str) -> str:
    arm = f"\n\nADDITIONAL ACQUISITION-DERIVED CONTEXT:\n{context}" if context else ""
    return f"""You are repairing a Python project from a failing protected regression test.
You may inspect only the visible buggy information below. Select 1-4 EXISTING Python production files most likely to require the repair.
Return exactly one JSON object and nothing else: {{"files":["relative/path.py"]}}.
Do not select tests, .git paths, non-Python files, or paths not present in the repository tree.

REPOSITORY TREE:\n{tree}\n\nPROTECTED REGRESSION FAILURE:\n{failure}\n\nPROTECTED TEST SOURCE:\n{tests}{arm}"""


def call2_prompt(*, tree: str, failure: str, tests: str, sources: str, context: str) -> str:
    arm = f"\n\nADDITIONAL ACQUISITION-DERIVED CONTEXT:\n{context}" if context else ""
    return f"""Repair the visible buggy Python production source so the protected regression passes while preserving unrelated behavior.
Return exactly one unified git diff and nothing else. Modify only the selected production files shown below. Do not modify tests, create/delete/rename files, use binary patches, or touch non-Python files.

REPOSITORY TREE:\n{tree}\n\nPROTECTED REGRESSION FAILURE:\n{failure}\n\nPROTECTED TEST SOURCE:\n{tests}\n\nSELECTED BUGGY SOURCE:\n{sources}{arm}"""


def competence_row(case: Mapping[str, Any], arm: str, ctx, *, stage: str, repaired: bool = False, **extra: Any) -> dict[str, Any]:
    return {
        "project": str(case["project"]), "bug_id": str(case["bug_id"]), "arm": arm,
        "classification": "competence", "repaired": repaired,
        "activated": ctx.activated, "false_activation": ctx.false_activation,
        "misapplication": False, "stage": stage, **extra,
    }


def infrastructure_row(case: Mapping[str, Any], arm: str, ctx, *, stage: str, **extra: Any) -> dict[str, Any]:
    return {
        "project": str(case["project"]), "bug_id": str(case["bug_id"]), "arm": arm,
        "classification": "infrastructure_error", "repaired": None,
        "activated": ctx.activated, "false_activation": ctx.false_activation,
        "misapplication": False, "stage": stage, **extra,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--causal-corpus", type=Path, required=True)
    ap.add_argument("--protected-tests", type=Path, required=True)
    ap.add_argument("--capability", type=Path, required=True)
    ap.add_argument("--raw-memory", type=Path, required=True)
    ap.add_argument("--bugsinpy", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--image36", default="cp3-python36")
    ap.add_argument("--image37", default="cp3-python37")
    ap.add_argument("--image38", default="cp3-python38")
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite protected evaluation")

    workspace = Path.cwd().resolve()
    causal = load_json(args.causal_corpus)
    capability = load_json(args.capability)
    raw_memory = load_json(args.raw_memory)
    protocol = load_json(Path(__file__).with_name("CHECKPOINT3_PROTECTED_EVAL_V1.json"))
    if protocol.get("protocol") != EVAL_PROTOCOL:
        raise SystemExit("protected evaluation protocol mismatch")
    protected = causal.get("protected")
    if not isinstance(protected, list) or not isinstance(raw_memory, list):
        raise SystemExit("invalid protected corpus or raw memory")
    public_rules = capability.get("rules")
    if not isinstance(public_rules, list) or not public_rules:
        raise SystemExit("frozen capability contains no admitted rules")
    rules = tuple(rule_from_public(row) for row in public_rules)
    limits = protocol["context_limits"]
    model = protocol["provider"]
    images = {"3.6": args.image36, "3.7": args.image37, "3.8": args.image38}

    from triskelion.providers import RiverProvider
    provider = RiverProvider(str(model["model"]))
    raw_text = raw_memory_context(raw_memory, int(limits["raw_memory_chars"]))
    args.out.mkdir(parents=True)
    patches_dir = args.out / "patches"
    patches_dir.mkdir()
    work_dir = args.out / "work"
    work_dir.mkdir()
    rows: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    for case_index, case in enumerate(protected):
        case_dir = work_dir / f"case-{case_index:02d}"
        case_dir.mkdir()
        repo = case_dir / "repo"
        checkout = clone_buggy(str(case["repository"]), str(case["buggy_commit"]), repo)
        try:
            test_text, test_paths = protected_test_text(args.protected_tests, case_index)
        except Exception as exc:
            test_text, test_paths = "", ()
            checkout = {"ok": False, "stage": "protected_test_bundle", "error": exc.__class__.__name__}
        try:
            image = docker_image_for(str(case["python_version_declared"]), images)
        except Exception as exc:
            image = ""
            checkout = {"ok": False, "stage": "python_version", "error": str(exc)}

        if checkout.get("ok"):
            bug_dir = args.bugsinpy / "projects" / str(case["project"]) / "bugs" / str(case["bug_id"])
            ok, prepared, raw_prepare = target_call(
                image=image, mode="prepare", repo=repo, buggy_commit=str(case["buggy_commit"]),
                bug_dir=bug_dir, bundle=args.protected_tests, case_index=case_index,
                workspace=workspace,
            )
        else:
            ok, prepared, raw_prepare = False, {}, ""
            bug_dir = args.bugsinpy

        if not checkout.get("ok") or not ok:
            dummy = type("Context", (), {"activated": False, "false_activation": False})()
            stage = str(checkout.get("stage") if not checkout.get("ok") else prepared.get("stage", "prepare"))
            for arm in ARMS:
                rows.append(infrastructure_row(case, arm, dummy, stage=stage, prepare_output=raw_prepare))
            continue

        try:
            tree = truncate_head_tail(repository_tree(repo), int(limits["repository_tree_chars"]))
            failure = truncate_head_tail(baseline_failure_text(prepared), int(limits["baseline_failure_chars"]))
            tests_visible = truncate_head_tail(test_text, int(limits["protected_test_source_chars"]))
        except Exception as exc:
            dummy = type("Context", (), {"activated": False, "false_activation": False})()
            for arm in ARMS:
                rows.append(infrastructure_row(case, arm, dummy, stage="visible_baseline", error=exc.__class__.__name__))
            continue
        scope_context = f"REPOSITORY TREE:\n{tree}\n\nREGRESSION FAILURE:\n{failure}\n\nTEST SOURCE:\n{tests_visible}"

        for arm_index, arm in enumerate(ARMS):
            ctx = arm_context(arm, visible_context=scope_context, rules=rules, raw_memory_text=raw_text)
            ctx_text = truncate_head_tail(ctx.text, int(limits["capability_context_chars"] if arm != "raw_memory" else limits["raw_memory_chars"])) if ctx.text else ""
            seed1 = int(model["seed_base"]) + case_index * 2
            seed2 = seed1 + 1
            prompt1 = call1_prompt(tree=tree, failure=failure, tests=tests_visible, context=ctx_text)
            try:
                response1 = provider.sample(prompt1, seed=seed1, max_tokens=int(model["max_tokens_per_call"]))
            except Exception as exc:
                rows.append(infrastructure_row(case, arm, ctx, stage="provider_call_1", error=exc.__class__.__name__))
                continue
            calls.append({"case_index": case_index, "arm": arm, "call": 1, "seed": seed1, "response": response1.to_dict()})
            try:
                selected = parse_file_selection(response1.text)
                sources = selected_source_text(repo, selected, test_paths=test_paths, limit=int(limits["selected_source_chars_total"]))
            except Exception as exc:
                rows.append(competence_row(case, arm, ctx, stage="call_1_invalid", model_error=exc.__class__.__name__))
                continue

            prompt2 = call2_prompt(tree=tree, failure=failure, tests=tests_visible, sources=sources, context=ctx_text)
            try:
                response2 = provider.sample(prompt2, seed=seed2, max_tokens=int(model["max_tokens_per_call"]))
            except Exception as exc:
                rows.append(infrastructure_row(case, arm, ctx, stage="provider_call_2", error=exc.__class__.__name__, selected_files=list(selected)))
                continue
            calls.append({"case_index": case_index, "arm": arm, "call": 2, "seed": seed2, "response": response2.to_dict()})
            try:
                diff = extract_unified_diff(response2.text)
                changed = validate_patch_safety(diff, protected_test_paths=test_paths, selected_paths=selected)
            except Exception as exc:
                rows.append(competence_row(case, arm, ctx, stage="call_2_invalid", selected_files=list(selected), model_error=exc.__class__.__name__))
                continue

            patch_path = patches_dir / f"case-{case_index:02d}-{arm}.diff"
            patch_path.write_text(diff)
            target_ok, target_result, raw_target = target_call(
                image=image, mode="evaluate", repo=repo, buggy_commit=str(case["buggy_commit"]),
                bug_dir=bug_dir, bundle=args.protected_tests, case_index=case_index,
                workspace=workspace, patch=patch_path,
            )
            if not target_result:
                rows.append(infrastructure_row(case, arm, ctx, stage="target_runner", target_output=raw_target, selected_files=list(selected), changed_files=list(changed)))
                continue
            classification = target_result.get("classification")
            if classification == "infrastructure_error" or not target_ok:
                rows.append(infrastructure_row(case, arm, ctx, stage=str(target_result.get("stage", "target_runner")), target=target_result, selected_files=list(selected), changed_files=list(changed)))
                continue
            repaired = bool(target_result.get("repaired"))
            patch_applied = bool(target_result.get("patch_applied"))
            test_executed = bool(target_result.get("test_executed"))
            rows.append({
                "project": str(case["project"]), "bug_id": str(case["bug_id"]), "arm": arm,
                "classification": "competence", "repaired": repaired,
                "activated": ctx.activated, "false_activation": ctx.false_activation,
                "misapplication": misapplication(activated=ctx.activated, patch_applied=patch_applied, test_executed=test_executed, repaired=repaired),
                "stage": str(target_result.get("stage", "complete")),
                "matched_rule_ids": list(ctx.matched_rule_ids), "selected_files": list(selected),
                "changed_files": list(changed), "patch_applied": patch_applied, "test_executed": test_executed,
                "target": target_result,
            })

    validated = validate_complete_four_arm_results(protected, rows)
    summary = summarize_four_arm_results(validated)
    result = {
        "protocol": EVAL_PROTOCOL,
        "capability_id": capability["capability_id"],
        "protected_case_count": len(protected),
        "row_count": len(validated),
        "summary": summary,
    }
    (args.out / "ROWS.json").write_text(json.dumps(validated, indent=2, sort_keys=True) + "\n")
    (args.out / "CALLS.json").write_text(json.dumps(calls, indent=2, sort_keys=True) + "\n")
    (args.out / "RESULTS.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
