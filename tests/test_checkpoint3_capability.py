from __future__ import annotations

import pytest

from triskelion_runtime.checkpoint3_capability import (
    capability_build_protocol_sha256,
    compile_rule,
    public_capability_payload,
    route_rules,
    rule_applies,
)


def valid_rule() -> dict:
    return {
        "title": "Guard missing mapping key before lookup",
        "required_any": ["keyerror", "missing key"],
        "required_all": ["mapping"],
        "forbidden_any": ["network timeout"],
        "repair_instruction": "Check membership before lookup and preserve the existing fallback behavior.",
    }


def test_compile_rule_and_deterministic_scope_match() -> None:
    rule = compile_rule(valid_rule(), evidence_project="exampleproj", evidence_bug_id="17")
    assert rule_applies(rule, "MAPPING lookup raised KeyError for a missing key") is True
    assert rule_applies(rule, "mapping lookup raised KeyError during a network timeout") is False
    assert rule_applies(rule, "KeyError without the required structure") is False


def test_route_returns_only_matching_rules_without_mutating_rule_identity() -> None:
    first = compile_rule(valid_rule(), evidence_project="exampleproj", evidence_bug_id="17")
    other_raw = {
        "title": "Normalize empty sequence boundary",
        "required_any": ["indexerror"],
        "required_all": ["sequence"],
        "forbidden_any": [],
        "repair_instruction": "Handle the empty sequence before indexing while preserving nonempty behavior.",
    }
    second = compile_rule(other_raw, evidence_project="otherproj", evidence_bug_id="22")
    routed = route_rules((first, second), "mapping KeyError missing key")
    assert routed == (first,)
    assert routed[0] is first


def test_compile_rule_rejects_project_identity_leakage() -> None:
    raw = valid_rule()
    raw["repair_instruction"] += " This was learned from ExampleProj."
    with pytest.raises(ValueError, match="forbidden acquisition identity"):
        compile_rule(raw, evidence_project="exampleproj", evidence_bug_id="17")


def test_compile_rule_rejects_bug_identity_phrase_but_not_ordinary_number() -> None:
    raw = valid_rule()
    raw["title"] = "Repair bug 17 by guarding lookup"
    with pytest.raises(ValueError, match="forbidden acquisition identity"):
        compile_rule(raw, evidence_project="exampleproj", evidence_bug_id="17")

    ordinary = valid_rule()
    ordinary["repair_instruction"] += " Preserve behavior for 17 ordinary inputs."
    compile_rule(ordinary, evidence_project="exampleproj", evidence_bug_id="17")


def test_compile_rule_rejects_commit_hash_and_absolute_path() -> None:
    raw = valid_rule()
    raw["repair_instruction"] = "Use behavior from commit deadbeef in /tmp/source/module.py"
    with pytest.raises(ValueError, match="forbidden acquisition identity"):
        compile_rule(raw, evidence_project="exampleproj", evidence_bug_id="17")


def test_compile_rule_rejects_verbatim_fixed_patch_fragment() -> None:
    raw = valid_rule()
    fixed_line = "if request_timeout is None: return default_timeout"
    raw["repair_instruction"] = f"Apply this exact change: {fixed_line}"
    with pytest.raises(ValueError, match="fixed patch"):
        compile_rule(
            raw,
            evidence_project="exampleproj",
            evidence_bug_id="17",
            forbidden_literals=[fixed_line],
        )


def test_compile_rule_requires_positive_scope_signature() -> None:
    raw = valid_rule()
    raw["required_any"] = []
    raw["required_all"] = []
    with pytest.raises(ValueError, match="positive signature"):
        compile_rule(raw, evidence_project="exampleproj", evidence_bug_id="17")


def test_public_capability_id_is_stable_and_hides_evidence_identity_and_failure_identity() -> None:
    rule = compile_rule(valid_rule(), evidence_project="exampleproj", evidence_bug_id="17")
    protocol_hash = capability_build_protocol_sha256()
    failures = [{
        "case_index": 0,
        "stage": "parse",
        "reason": "invalid_json",
        "project": "exampleproj",
        "bug_id": "17",
    }]
    first = public_capability_payload((rule,), build_protocol_sha256=protocol_hash, compile_failures=failures)
    second = public_capability_payload((rule,), build_protocol_sha256=protocol_hash, compile_failures=failures)
    assert first == second
    serialized = str(first).casefold()
    assert "exampleproj" not in serialized
    assert "evidence_bug_id" not in serialized
    assert "bug_id" not in serialized
    assert len(first["capability_id"]) == 64
