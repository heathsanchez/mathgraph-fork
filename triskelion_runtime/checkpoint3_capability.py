from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

CAPABILITY_BUILD_PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_CAPABILITY_BUILD_V1"
MAX_SIGNATURES = 8
MIN_SIGNATURE_CHARS = 2
MAX_SIGNATURE_CHARS = 80
MAX_INSTRUCTION_CHARS = 1200
COMMIT_RE = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
ABSOLUTE_PATH_RE = re.compile(r"(?:^|\s)(?:/[^\s]+|[A-Za-z]:\\[^\s]+)")


@dataclass(frozen=True)
class RepairRule:
    rule_id: str
    title: str
    required_any: tuple[str, ...]
    required_all: tuple[str, ...]
    forbidden_any: tuple[str, ...]
    repair_instruction: str
    evidence_project: str
    evidence_bug_id: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "required_any": list(self.required_any),
            "required_all": list(self.required_all),
            "forbidden_any": list(self.forbidden_any),
            "repair_instruction": self.repair_instruction,
        }


def normalize_context(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(text.split())


def _clean_signatures(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be an array")
    if len(value) > MAX_SIGNATURES:
        raise ValueError(f"{field} exceeds max signatures")
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError(f"{field} entries must be strings")
        signature = normalize_context(raw)
        if not (MIN_SIGNATURE_CHARS <= len(signature) <= MAX_SIGNATURE_CHARS):
            raise ValueError(f"{field} signature length out of bounds")
        if signature not in seen:
            out.append(signature)
            seen.add(signature)
    return tuple(out)


def _contains_forbidden_identity(text: str, *, project: str, bug_id: str) -> bool:
    normalized = normalize_context(text)
    project_norm = normalize_context(project)
    if project_norm and project_norm in normalized:
        return True
    if bug_id and re.search(rf"(?<!\w){re.escape(str(bug_id))}(?!\w)", normalized):
        return True
    if COMMIT_RE.search(text):
        return True
    if ABSOLUTE_PATH_RE.search(text):
        return True
    return False


def compile_rule(
    raw: Mapping[str, Any],
    *,
    evidence_project: str,
    evidence_bug_id: str,
) -> RepairRule:
    title = raw.get("title")
    instruction = raw.get("repair_instruction")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("repair_instruction must be a non-empty string")
    title = " ".join(title.split())
    instruction = instruction.strip()
    if len(instruction) > MAX_INSTRUCTION_CHARS:
        raise ValueError("repair_instruction exceeds maximum length")

    required_any = _clean_signatures(raw.get("required_any"), "required_any")
    required_all = _clean_signatures(raw.get("required_all"), "required_all")
    forbidden_any = _clean_signatures(raw.get("forbidden_any"), "forbidden_any")
    if not required_any and not required_all:
        raise ValueError("at least one positive signature is required")

    identity_fields = [title, instruction, *required_any, *required_all, *forbidden_any]
    if any(
        _contains_forbidden_identity(
            text, project=evidence_project, bug_id=evidence_bug_id
        )
        for text in identity_fields
    ):
        raise ValueError("compiler output contains forbidden acquisition identity")

    public = {
        "title": title,
        "required_any": required_any,
        "required_all": required_all,
        "forbidden_any": forbidden_any,
        "repair_instruction": instruction,
    }
    rule_id = hashlib.sha256(
        json.dumps(public, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()[:20]
    return RepairRule(
        rule_id=rule_id,
        title=title,
        required_any=required_any,
        required_all=required_all,
        forbidden_any=forbidden_any,
        repair_instruction=instruction,
        evidence_project=evidence_project,
        evidence_bug_id=evidence_bug_id,
    )


def rule_applies(rule: RepairRule, visible_context: str) -> bool:
    context = normalize_context(visible_context)
    if any(signature in context for signature in rule.forbidden_any):
        return False
    if any(signature not in context for signature in rule.required_all):
        return False
    if rule.required_any:
        return any(signature in context for signature in rule.required_any)
    return bool(rule.required_all)


def route_rules(rules: Sequence[RepairRule], visible_context: str) -> tuple[RepairRule, ...]:
    return tuple(rule for rule in rules if rule_applies(rule, visible_context))


def public_capability_payload(
    rules: Sequence[RepairRule],
    *,
    build_protocol_sha256: str,
    compile_failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    public_rules = [rule.to_public_dict() for rule in rules]
    payload = {
        "build_protocol": CAPABILITY_BUILD_PROTOCOL,
        "build_protocol_sha256": build_protocol_sha256,
        "rules": public_rules,
        "compile_failures": [dict(row) for row in compile_failures],
    }
    capability_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return {"capability_id": capability_id, **payload}


def capability_build_protocol_path() -> Path:
    return Path(__file__).with_name("CHECKPOINT3_CAPABILITY_BUILD_V1.json")


def capability_build_protocol_sha256() -> str:
    return hashlib.sha256(capability_build_protocol_path().read_bytes()).hexdigest()
