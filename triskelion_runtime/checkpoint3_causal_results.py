from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from triskelion_runtime.checkpoint3_causal_protocol import EXPECTED_ARMS

COMPETENCE = "competence"
INFRASTRUCTURE_ERROR = "infrastructure_error"
EXPECTED_CLASSIFICATIONS = {COMPETENCE, INFRASTRUCTURE_ERROR}


def _case_key(row: Mapping[str, Any]) -> tuple[str, str]:
    project = row.get("project")
    bug_id = row.get("bug_id")
    if not isinstance(project, str) or not project:
        raise ValueError("row project must be non-empty")
    if not isinstance(bug_id, str) or not bug_id:
        raise ValueError("row bug_id must be non-empty")
    return project, bug_id


def validate_complete_four_arm_results(
    protected_cases: Iterable[Mapping[str, Any]],
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    cases = []
    expected: set[tuple[str, str, str]] = set()
    for case in protected_cases:
        project, bug_id = _case_key(case)
        if case.get("split") != "protected":
            raise ValueError(f"evaluation case must be protected: {project}/{bug_id}")
        cases.append((project, bug_id))
        for arm in EXPECTED_ARMS:
            expected.add((project, bug_id, arm))

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in rows:
        row = dict(raw)
        project, bug_id = _case_key(row)
        arm = row.get("arm")
        if arm not in EXPECTED_ARMS:
            raise ValueError(f"unexpected arm: {arm}")
        key = (project, bug_id, arm)
        if key in seen:
            raise ValueError(f"duplicate case-arm outcome: {project}/{bug_id}/{arm}")
        seen.add(key)
        if key not in expected:
            raise ValueError(f"outcome outside frozen protected corpus: {project}/{bug_id}/{arm}")

        classification = row.get("classification")
        if classification not in EXPECTED_CLASSIFICATIONS:
            raise ValueError(f"unexpected classification: {classification}")
        if classification == COMPETENCE:
            if not isinstance(row.get("repaired"), bool):
                raise ValueError("competence outcome requires boolean repaired")
        else:
            if row.get("repaired") is not None:
                raise ValueError("infrastructure outcome must set repaired to null")

        for field in ("activated", "false_activation", "misapplication"):
            if not isinstance(row.get(field), bool):
                raise ValueError(f"{field} must be boolean")
        normalized.append(row)

    missing = expected - seen
    if missing:
        sample = sorted(missing)[0]
        raise ValueError(f"missing frozen case-arm outcome: {sample[0]}/{sample[1]}/{sample[2]}")
    return normalized


def summarize_four_arm_results(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        arm = row.get("arm")
        if arm not in EXPECTED_ARMS:
            raise ValueError(f"unexpected arm: {arm}")
        by_arm[str(arm)].append(row)

    summary: dict[str, Any] = {}
    for arm in EXPECTED_ARMS:
        arm_rows = by_arm.get(arm, [])
        competence = [r for r in arm_rows if r.get("classification") == COMPETENCE]
        infrastructure = [r for r in arm_rows if r.get("classification") == INFRASTRUCTURE_ERROR]
        repaired = sum(bool(r.get("repaired")) for r in competence)
        total = len(arm_rows)
        evaluable = len(competence)
        summary[arm] = {
            "protected_case_count": total,
            "evaluable_count": evaluable,
            "repair_successes": repaired,
            "protected_repair_success_rate": (repaired / evaluable) if evaluable else None,
            "evaluable_coverage": (evaluable / total) if total else None,
            "infrastructure_error_rate": (len(infrastructure) / total) if total else None,
            "activation_rate": (sum(bool(r.get("activated")) for r in arm_rows) / total) if total else None,
            "false_activation_rate": (
                sum(bool(r.get("false_activation")) for r in arm_rows) / total
            ) if total else None,
            "misapplication_rate": (
                sum(bool(r.get("misapplication")) for r in arm_rows) / total
            ) if total else None,
        }
    return summary
