from __future__ import annotations

import pytest

from triskelion_runtime.checkpoint3_capability import RepairRule
from triskelion_runtime.checkpoint3_eval_core import (
    arm_context,
    extract_unified_diff,
    misapplication,
    parse_file_selection,
    validate_patch_safety,
)


def rule(rule_id: str, signature: str) -> RepairRule:
    return RepairRule(
        rule_id=rule_id,
        title=f"Rule {rule_id}",
        required_any=(signature,),
        required_all=(),
        forbidden_any=(),
        repair_instruction=f"Repair mechanism {rule_id}",
        evidence_project="",
        evidence_bug_id="",
    )


def test_file_selection_requires_exact_safe_python_paths() -> None:
    assert parse_file_selection('{"files":["pkg/a.py","pkg/b.py"]}') == ("pkg/a.py", "pkg/b.py")
    with pytest.raises(ValueError, match="Python files"):
        parse_file_selection('{"files":["README.md"]}')
    with pytest.raises(ValueError, match="unsafe"):
        parse_file_selection('{"files":["../secret.py"]}')
    with pytest.raises(ValueError, match="count"):
        parse_file_selection('{"files":[]}' )


def test_extract_diff_and_patch_safety_forbid_test_edits_and_unselected_files() -> None:
    response = """```diff
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -1 +1 @@
-old = 1
+old = 2
```"""
    diff = extract_unified_diff(response)
    assert validate_patch_safety(
        diff,
        protected_test_paths=("tests/test_core.py",),
        selected_paths=("pkg/core.py",),
    ) == ("pkg/core.py",)

    with pytest.raises(ValueError, match="outside call-1 selection"):
        validate_patch_safety(
            diff,
            protected_test_paths=("tests/test_core.py",),
            selected_paths=("pkg/other.py",),
        )

    bad = """--- a/tests/test_core.py
+++ b/tests/test_core.py
@@ -1 +1 @@
-assert False
+assert True
"""
    with pytest.raises(ValueError, match="test modification"):
        validate_patch_safety(bad, protected_test_paths=("tests/test_core.py",))


def test_patch_safety_forbids_creation_rename_binary_and_non_python() -> None:
    creation = """--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1 @@
+x = 1
"""
    with pytest.raises(ValueError, match="creation/deletion"):
        validate_patch_safety(creation, protected_test_paths=())

    rename = """--- a/pkg/a.py
+++ b/pkg/b.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
    with pytest.raises(ValueError, match="rename"):
        validate_patch_safety(rename, protected_test_paths=())

    non_python = """--- a/config.txt
+++ b/config.txt
@@ -1 +1 @@
-a
+b
"""
    with pytest.raises(ValueError, match="Python production"):
        validate_patch_safety(non_python, protected_test_paths=())

    binary = "GIT binary patch\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
    with pytest.raises(ValueError, match="binary"):
        validate_patch_safety(binary, protected_test_paths=())


def test_always_on_and_verified_use_same_rules_but_different_scope() -> None:
    rules = (rule("r1", "keyerror"), rule("r2", "indexerror"))
    visible = "mapping operation raised KeyError"
    always = arm_context("always_on", visible_context=visible, rules=rules, raw_memory_text="raw")
    verified = arm_context("verified", visible_context=visible, rules=rules, raw_memory_text="raw")
    assert always.activated is True
    assert "r1" in always.text and "r2" in always.text
    assert verified.activated is True
    assert "r1" in verified.text and "r2" not in verified.text
    assert always.matched_rule_ids == verified.matched_rule_ids == ("r1",)
    assert always.false_activation is False
    assert verified.false_activation is False


def test_false_activation_is_deterministic_for_always_on_only() -> None:
    rules = (rule("r1", "keyerror"),)
    always = arm_context("always_on", visible_context="unrelated typeerror", rules=rules, raw_memory_text="raw")
    verified = arm_context("verified", visible_context="unrelated typeerror", rules=rules, raw_memory_text="raw")
    assert always.activated is True and always.false_activation is True
    assert verified.activated is False and verified.false_activation is False


def test_cold_and_raw_never_count_as_activation() -> None:
    rules = (rule("r1", "keyerror"),)
    cold = arm_context("cold", visible_context="keyerror", rules=rules, raw_memory_text="RAW")
    raw = arm_context("raw_memory", visible_context="keyerror", rules=rules, raw_memory_text="RAW")
    assert cold.activated is False and cold.text == ""
    assert raw.activated is False and raw.text == "RAW"


def test_misapplication_requires_activated_applied_and_executed_failure() -> None:
    assert misapplication(activated=True, patch_applied=True, test_executed=True, repaired=False) is True
    assert misapplication(activated=False, patch_applied=True, test_executed=True, repaired=False) is False
    assert misapplication(activated=True, patch_applied=False, test_executed=False, repaired=False) is False
    assert misapplication(activated=True, patch_applied=True, test_executed=True, repaired=True) is False
