from __future__ import annotations

import json

import pytest

from triskelion_runtime.checkpoint3_build_capability import (
    OMISSION,
    added_patch_literals,
    parse_rule_object,
    qualified_attempt_for,
    regression_output,
    truncate_head_tail,
)


def test_truncate_head_tail_is_deterministic_and_bounded() -> None:
    text = "0123456789" * 50
    out = truncate_head_tail(text, 120)
    assert len(out) == 120
    assert OMISSION in out
    assert out.startswith(text[:20])
    assert out.endswith(text[-20:])
    assert truncate_head_tail("short", 120) == "short"


def test_added_patch_literals_extracts_only_added_nonheader_lines() -> None:
    diff = """--- a/x.py
+++ b/x.py
@@ -1 +1 @@
-old thing
+if request_timeout is None: return default_timeout
+tiny
"""
    assert added_patch_literals(diff) == [
        "if request_timeout is None: return default_timeout"
    ]


def test_parse_rule_object_accepts_last_schema_complete_json_candidate() -> None:
    first = {
        "title": "First",
        "required_any": ["a"],
        "required_all": [],
        "forbidden_any": [],
        "repair_instruction": "first",
    }
    second = {
        "title": "Second",
        "required_any": ["b"],
        "required_all": [],
        "forbidden_any": [],
        "repair_instruction": "second",
    }
    text = f"```json\n{json.dumps(first)}\n```\nnoise\n```json\n{json.dumps(second)}\n```"
    assert parse_rule_object(text)["title"] == "Second"


def test_parse_rule_object_rejects_incomplete_output() -> None:
    with pytest.raises(ValueError, match="schema-complete"):
        parse_rule_object('{"title":"missing fields"}')


def test_qualified_attempt_for_requires_exact_unique_match() -> None:
    attempts = [
        {"project": "p", "bug_id": "1", "classification": "infrastructure_negative"},
        {"project": "p", "bug_id": "1", "classification": "qualified", "fixed": {}, "buggy": {}},
    ]
    assert qualified_attempt_for(attempts, "p", "1")["classification"] == "qualified"
    with pytest.raises(ValueError, match="exactly one"):
        qualified_attempt_for(attempts, "p", "2")


def test_regression_output_preserves_commands_outputs_and_returncodes() -> None:
    attempt = {
        "buggy": {
            "test": {
                "steps": [
                    {"command": "pytest -q test_x.py", "output": "FAILED x", "returncode": 1},
                    {"command": "python smoke.py", "output": "ok", "returncode": 0},
                ]
            }
        }
    }
    text = regression_output(attempt, "buggy")
    assert "$ pytest -q test_x.py" in text
    assert "FAILED x" in text
    assert "[returncode=1]" in text
    assert "$ python smoke.py" in text
