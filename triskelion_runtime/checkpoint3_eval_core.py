from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from triskelion_runtime.checkpoint3_capability import RepairRule, route_rules

ARMS = ("cold", "raw_memory", "always_on", "verified")
DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
DIFF_HEADER_RE = re.compile(r"^(?:---|\+\+\+)\s+([^\t\n]+)", re.MULTILINE)


@dataclass(frozen=True)
class ArmContext:
    arm: str
    text: str
    activated: bool
    matched_rule_ids: tuple[str, ...]
    false_activation: bool


def safe_repo_path(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    if value.startswith(("a/", "b/")):
        value = value[2:]
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or ":" in value
        or value.startswith(".git/")
        or value == ".git"
    ):
        raise ValueError(f"unsafe repository path: {raw}")
    return str(path)


def parse_file_selection(text: str, *, max_files: int = 4) -> tuple[str, ...]:
    candidates: list[str] = [text.strip()]
    candidates.extend(match.group(1).strip() for match in JSON_FENCE_RE.finditer(text))
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    parsed = None
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, Mapping) and set(value) == {"files"} and isinstance(value["files"], list):
            parsed = value["files"]
    if parsed is None:
        raise ValueError("no exact file-selection JSON object found")
    if not 1 <= len(parsed) <= max_files:
        raise ValueError("file selection count out of bounds")
    out: list[str] = []
    for raw in parsed:
        if not isinstance(raw, str):
            raise ValueError("selected files must be strings")
        path = safe_repo_path(raw)
        if not path.endswith(".py"):
            raise ValueError("selected production files must be Python files")
        if path not in out:
            out.append(path)
    if not out:
        raise ValueError("empty deduplicated file selection")
    return tuple(out)


def extract_unified_diff(text: str) -> str:
    candidates = [match.group(1).strip() for match in DIFF_FENCE_RE.finditer(text)]
    stripped = text.strip()
    if stripped.startswith("diff --git ") or ("--- " in stripped and "+++ " in stripped):
        candidates.append(stripped)
    valid = [candidate for candidate in candidates if "--- " in candidate and "+++ " in candidate]
    if not valid:
        raise ValueError("no unified diff found")
    return valid[-1] + "\n"


def patch_paths(diff_text: str) -> tuple[str, ...]:
    headers = DIFF_HEADER_RE.findall(diff_text)
    if not headers or len(headers) % 2 != 0:
        raise ValueError("malformed unified diff headers")
    paired: list[str] = []
    for index in range(0, len(headers), 2):
        raw_before, raw_after = headers[index].strip(), headers[index + 1].strip()
        if raw_before == "/dev/null" or raw_after == "/dev/null":
            raise ValueError("file creation/deletion is outside frozen patch contract")
        before, after = safe_repo_path(raw_before), safe_repo_path(raw_after)
        if before != after:
            raise ValueError("patch may not rename files")
        if before not in paired:
            paired.append(before)
    return tuple(paired)


def validate_patch_safety(
    diff_text: str,
    *,
    protected_test_paths: Sequence[str],
    selected_paths: Sequence[str] = (),
) -> tuple[str, ...]:
    if "GIT binary patch" in diff_text or "Binary files " in diff_text:
        raise ValueError("binary patch forbidden")
    changed = patch_paths(diff_text)
    tests = {safe_repo_path(path) for path in protected_test_paths}
    selected = {safe_repo_path(path) for path in selected_paths}
    for path in changed:
        if path in tests:
            raise ValueError("protected regression test modification forbidden")
        if not path.endswith(".py"):
            raise ValueError("only Python production files may be modified")
        if selected and path not in selected:
            raise ValueError("patch changed a file outside call-1 selection")
    return changed


def rule_from_public(raw: Mapping[str, Any]) -> RepairRule:
    required = {"rule_id", "title", "required_any", "required_all", "forbidden_any", "repair_instruction"}
    if set(raw) != required:
        raise ValueError("public capability rule fields must be exact")
    return RepairRule(
        rule_id=str(raw["rule_id"]), title=str(raw["title"]),
        required_any=tuple(str(x) for x in raw["required_any"]),
        required_all=tuple(str(x) for x in raw["required_all"]),
        forbidden_any=tuple(str(x) for x in raw["forbidden_any"]),
        repair_instruction=str(raw["repair_instruction"]), evidence_project="", evidence_bug_id="",
    )


def format_rules(rules: Sequence[RepairRule]) -> str:
    if not rules:
        return ""
    return "\n\n".join(f"RULE {rule.rule_id}: {rule.title}\n{rule.repair_instruction}" for rule in rules)


def arm_context(arm: str, *, visible_context: str, rules: Sequence[RepairRule], raw_memory_text: str) -> ArmContext:
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    matched = route_rules(rules, visible_context)
    matched_ids = tuple(rule.rule_id for rule in matched)
    if arm == "cold":
        return ArmContext(arm, "", False, matched_ids, False)
    if arm == "raw_memory":
        return ArmContext(arm, raw_memory_text, False, matched_ids, False)
    if arm == "always_on":
        activated = bool(rules)
        return ArmContext(arm, format_rules(rules), activated, matched_ids, activated and not bool(matched))
    activated = bool(matched)
    return ArmContext(arm, format_rules(matched), activated, matched_ids, False)


def misapplication(*, activated: bool, patch_applied: bool, test_executed: bool, repaired: bool) -> bool:
    return bool(activated and patch_applied and test_executed and not repaired)
