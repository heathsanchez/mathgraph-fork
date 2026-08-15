from __future__ import annotations

import pytest

from triskelion_runtime.checkpoint3_causal_protocol import EXPECTED_ARMS
from triskelion_runtime.checkpoint3_causal_results import (
    validate_complete_four_arm_results,
    summarize_four_arm_results,
)


def protected_cases() -> list[dict]:
    return [{"project": "black", "bug_id": "18", "split": "protected"}]


def complete_rows() -> list[dict]:
    return [
        {
            "project": "black",
            "bug_id": "18",
            "arm": arm,
            "classification": "competence",
            "repaired": arm == "verified",
            "activated": arm in ("always_on", "verified"),
            "false_activation": arm == "always_on",
            "misapplication": False,
        }
        for arm in EXPECTED_ARMS
    ]


def test_complete_four_arm_contract_and_summary() -> None:
    rows = validate_complete_four_arm_results(protected_cases(), complete_rows())
    summary = summarize_four_arm_results(rows)

    assert summary["verified"]["protected_repair_success_rate"] == 1.0
    assert summary["cold"]["protected_repair_success_rate"] == 0.0
    assert summary["always_on"]["false_activation_rate"] == 1.0
    assert summary["verified"]["evaluable_coverage"] == 1.0


def test_missing_arm_is_rejected() -> None:
    rows = complete_rows()[:-1]
    with pytest.raises(ValueError, match="missing frozen case-arm outcome"):
        validate_complete_four_arm_results(protected_cases(), rows)


def test_duplicate_arm_is_rejected() -> None:
    rows = complete_rows()
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="duplicate case-arm outcome"):
        validate_complete_four_arm_results(protected_cases(), rows)


def test_infrastructure_error_is_not_counted_as_repair_failure() -> None:
    rows = complete_rows()
    rows[0]["classification"] = "infrastructure_error"
    rows[0]["repaired"] = None
    validated = validate_complete_four_arm_results(protected_cases(), rows)
    summary = summarize_four_arm_results(validated)

    assert summary["cold"]["protected_repair_success_rate"] is None
    assert summary["cold"]["evaluable_coverage"] == 0.0
    assert summary["cold"]["infrastructure_error_rate"] == 1.0
