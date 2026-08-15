from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from triskelion_runtime.checkpoint3_capability import (
    capability_build_protocol_path,
    capability_build_protocol_sha256,
    compile_rule,
    public_capability_payload,
)

REQUIRED_RULE_FIELDS = {
    "title",
    "required_any",
    "required_all",
    "forbidden_any",
    "repair_instruction",
}
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
OMISSION = "\n... [FROZEN EVIDENCE TRUNCATION] ...\n"


def truncate_head_tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= len(OMISSION) + 2:
        raise ValueError("truncation limit too small")
    remaining = limit - len(OMISSION)
    head = remaining // 2
    tail = remaining - head
    return text[:head] + OMISSION + text[-tail:]


def qualified_attempt_for(
    attempts: Sequence[Mapping[str, Any]], project: str, bug_id: str
) -> Mapping[str, Any]:
    matches = [
        row
        for row in attempts
        if row.get("project") == project
        and str(row.get("bug_id")) == str(bug_id)
        and row.get("classification") == "qualified"
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one qualified attempt for {project}/{bug_id}; got {len(matches)}"
        )
    return matches[0]


def regression_output(attempt: Mapping[str, Any], side: str) -> str:
    side_result = attempt.get(side)
    if not isinstance(side_result, Mapping):
        raise ValueError(f"missing {side} qualification evidence")
    test = side_result.get("test")
    if not isinstance(test, Mapping):
        raise ValueError(f"missing {side}.test qualification evidence")
    steps = test.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"missing {side}.test.steps qualification evidence")
    chunks: list[str] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        command = step.get("command")
        output = step.get("output")
        if command:
            chunks.append(f"$ {command}")
        if output:
            chunks.append(str(output))
        chunks.append(f"[returncode={step.get('returncode')}]")
    return "\n".join(chunks)


def added_patch_literals(diff_text: str) -> list[str]:
    literals: list[str] = []
    seen: set[str] = set()
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        literal = line[1:].strip()
        if len(literal) < 16 or literal in seen:
            continue
        seen.add(literal)
        literals.append(literal)
    return literals


def parse_rule_object(text: str) -> Mapping[str, Any]:
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    candidates.extend(match.group(1).strip() for match in FENCE_RE.finditer(text))
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])

    accepted: list[Mapping[str, Any]] = []
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, Mapping) and REQUIRED_RULE_FIELDS.issubset(value):
            accepted.append(value)
    if not accepted:
        raise ValueError("no schema-complete JSON rule object found")
    return accepted[-1]


def compiler_prompt(*, gold_diff: str, buggy_output: str, fixed_output: str) -> str:
    return f"""You are compiling ONE reusable code-repair capability from a verified acquisition example.

Your output must be one JSON object and nothing else with exactly these fields:
{{
  "title": "short mechanism-level name",
  "required_any": ["short literal signature", "..."],
  "required_all": ["short literal signature", "..."],
  "forbidden_any": ["short literal signature", "..."],
  "repair_instruction": "general repair action, not an exact patch"
}}

Rules:
- Generalize the MECHANISM, not this repository or bug identity.
- Do not name the project, bug ID, commits, file paths, or reproduce an exact fixed code line.
- Signatures must be literal strings likely to appear in a future buggy source or regression failure.
- Use at most 8 strings in each signature list.
- At least one positive signature is required across required_any/required_all.
- repair_instruction must be <=1200 characters and describe what to change while preserving unaffected behavior.
- If the evidence suggests exception/control-flow handling, say so generally; likewise for boundary, state, API, shape, typing, ordering, fallback, parsing, or resource-lifetime mechanisms.

BUGGY REGRESSION EVIDENCE:
{buggy_output}

FIXED REGRESSION EVIDENCE:
{fixed_output}

VERIFIED BUGGY->FIXED DIFF:
{gold_diff}
"""


def git_diff_exact(repository: str, buggy: str, fixed: str, timeout: int = 180) -> str:
    with tempfile.TemporaryDirectory(prefix="triskelion_cp3_cap_") as td:
        repo = Path(td) / "repo"
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True, timeout=timeout)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", repository],
            check=True,
            timeout=timeout,
        )
        for commit in (buggy, fixed):
            subprocess.run(
                ["git", "-C", str(repo), "fetch", "--quiet", "--depth=1", "origin", commit],
                check=True,
                timeout=timeout,
            )
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "diff",
                "--no-ext-diff",
                "--unified=5",
                buggy,
                fixed,
                "--",
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        if not proc.stdout.strip():
            raise RuntimeError("empty exact buggy-to-fixed diff")
        return proc.stdout


def load_build_protocol() -> Mapping[str, Any]:
    value = json.loads(capability_build_protocol_path().read_text())
    if not isinstance(value, Mapping):
        raise ValueError("capability build protocol root must be an object")
    return value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--causal-corpus", type=Path, required=True)
    ap.add_argument("--qualification-attempts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen capability build")

    build_protocol = load_build_protocol()
    causal = json.loads(args.causal_corpus.read_text())
    attempts = json.loads(args.qualification_attempts.read_text())
    if not isinstance(causal, Mapping) or not isinstance(attempts, list):
        raise SystemExit("invalid causal corpus or qualification attempts")
    acquisition = causal.get("acquisition")
    protected = causal.get("protected")
    if not isinstance(acquisition, list) or not isinstance(protected, list):
        raise SystemExit("causal corpus missing split arrays")
    if protected and any("fixed_commit" in row for row in protected if isinstance(row, Mapping)):
        raise SystemExit("protected corpus contains forbidden fixed commit")

    compiler = build_protocol["compiler"]
    evidence_cfg = build_protocol["evidence_reconstruction"]
    seed_base = int(compiler["seed_base"])
    max_tokens = int(compiler["max_tokens"])

    # Lazy import keeps deterministic schema/unit tests independent of the River dependency.
    from triskelion.providers import RiverProvider

    provider = RiverProvider(str(compiler["model"]))
    rules = []
    compile_failures: list[dict[str, Any]] = []
    raw_memory: list[dict[str, Any]] = []
    compiler_calls: list[dict[str, Any]] = []

    for case_index, case in enumerate(acquisition):
        if not isinstance(case, Mapping):
            raise SystemExit("acquisition case must be an object")
        project = str(case["project"])
        bug_id = str(case["bug_id"])
        attempt = qualified_attempt_for(attempts, project, bug_id)
        try:
            diff = git_diff_exact(
                str(case["repository"]),
                str(case["buggy_commit"]),
                str(case["fixed_commit"]),
            )
        except Exception as exc:
            raise SystemExit(
                f"acquisition evidence reconstruction failed for index {case_index}: {exc.__class__.__name__}"
            ) from exc

        buggy_output = regression_output(attempt, "buggy")
        fixed_output = regression_output(attempt, "fixed")
        diff_visible = truncate_head_tail(diff, int(evidence_cfg["max_gold_diff_chars"]))
        buggy_visible = truncate_head_tail(
            buggy_output, int(evidence_cfg["max_buggy_regression_chars"])
        )
        fixed_visible = truncate_head_tail(
            fixed_output, int(evidence_cfg["max_fixed_regression_chars"])
        )
        raw_memory.append(
            {
                "case_index": case_index,
                "project": project,
                "bug_id": bug_id,
                "buggy_regression": buggy_visible,
                "fixed_regression": fixed_visible,
                "gold_diff": diff_visible,
            }
        )
        prompt = compiler_prompt(
            gold_diff=diff_visible,
            buggy_output=buggy_visible,
            fixed_output=fixed_visible,
        )
        seed = seed_base + case_index
        try:
            response = provider.sample(prompt, seed=seed, max_tokens=max_tokens)
        except Exception as exc:
            raise SystemExit(
                f"compiler provider failure at acquisition index {case_index}: {exc.__class__.__name__}"
            ) from exc

        response_row = response.to_dict()
        compiler_calls.append(
            {
                "case_index": case_index,
                "project": project,
                "bug_id": bug_id,
                "seed": seed,
                "response": response_row,
            }
        )
        try:
            raw_rule = parse_rule_object(response.text)
        except Exception:
            compile_failures.append(
                {"case_index": case_index, "stage": "parse", "reason": "invalid_rule_json"}
            )
            continue
        try:
            rule = compile_rule(
                raw_rule,
                evidence_project=project,
                evidence_bug_id=bug_id,
                forbidden_literals=added_patch_literals(diff),
            )
        except Exception:
            compile_failures.append(
                {"case_index": case_index, "stage": "admission", "reason": "rule_contract_rejected"}
            )
            continue
        rules.append(rule)

    minimum = int(build_protocol["admission_policy"]["minimum_admitted_rules_for_protected_evaluation"])
    if len(rules) < minimum:
        raise SystemExit(
            f"capability construction negative: admitted {len(rules)} rules; minimum is {minimum}"
        )

    protocol_hash = capability_build_protocol_sha256()
    capability = public_capability_payload(
        rules,
        build_protocol_sha256=protocol_hash,
        compile_failures=compile_failures,
    )
    summary = {
        "build_protocol": build_protocol["protocol"],
        "build_protocol_sha256": protocol_hash,
        "acquisition_case_count": len(acquisition),
        "compiler_call_count": len(compiler_calls),
        "admitted_rule_count": len(rules),
        "compile_failure_count": len(compile_failures),
        "capability_id": capability["capability_id"],
    }

    args.out.mkdir(parents=True)
    (args.out / "CAPABILITY.json").write_text(
        json.dumps(capability, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "RAW_MEMORY.json").write_text(
        json.dumps(raw_memory, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "COMPILER_CALLS.json").write_text(
        json.dumps(compiler_calls, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "BUILD_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
