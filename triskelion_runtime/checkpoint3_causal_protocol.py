from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

PROTOCOL_ID = "TRISKELION_BUGSINPY_CHECKPOINT3_CAUSAL_V1"
QUALIFICATION_PROTOCOL_ID = "TRISKELION_BUGSINPY_CHECKPOINT3_QUALIFICATION_V1"
EXPECTED_ARMS = ("cold", "raw_memory", "always_on", "verified")
EXPECTED_PRIMARY_ENDPOINT = "protected_repair_success_rate"


@dataclass(frozen=True)
class Checkpoint3CausalProtocol:
    protocol: str
    qualification_protocol: str
    upstream_commit: str
    arms: tuple[str, ...]
    primary_endpoint: str
    primary_endpoint_denominator: str
    stopping_rule: str
    frozen_before_protected_evaluation: bool
    raw: Mapping[str, Any]


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_true(value: Any, field: str) -> bool:
    if value is not True:
        raise ValueError(f"{field} must be true")
    return True


def validate_protocol(data: Mapping[str, Any]) -> Checkpoint3CausalProtocol:
    protocol = _require_string(data.get("protocol"), "protocol")
    if protocol != PROTOCOL_ID:
        raise ValueError(f"unexpected protocol: {protocol}")

    qualification_protocol = _require_string(
        data.get("qualification_protocol"), "qualification_protocol"
    )
    if qualification_protocol != QUALIFICATION_PROTOCOL_ID:
        raise ValueError(f"unexpected qualification_protocol: {qualification_protocol}")

    upstream_commit = _require_string(data.get("upstream_commit"), "upstream_commit")
    _require_true(
        data.get("frozen_before_protected_evaluation"),
        "frozen_before_protected_evaluation",
    )

    arms_value = data.get("arms")
    if not isinstance(arms_value, Sequence) or isinstance(arms_value, (str, bytes)):
        raise ValueError("arms must be an array")
    arms = tuple(str(arm) for arm in arms_value)
    if arms != EXPECTED_ARMS:
        raise ValueError(f"arms must be exactly {EXPECTED_ARMS}")

    acquisition = _require_mapping(data.get("acquisition_policy"), "acquisition_policy")
    if acquisition.get("source_split") != "acquisition":
        raise ValueError("acquisition_policy.source_split must be acquisition")
    if acquisition.get("protected_source_access") != "forbidden":
        raise ValueError("protected source access must be forbidden during capability building")
    if acquisition.get("protected_outcome_access") != "forbidden":
        raise ValueError("protected outcome access must be forbidden during capability building")

    evaluation = _require_mapping(data.get("evaluation_policy"), "evaluation_policy")
    if evaluation.get("source_split") != "protected":
        raise ValueError("evaluation_policy.source_split must be protected")
    for field in (
        "gold_patch_hidden",
        "same_model_across_arms",
        "same_task_order_across_arms",
        "same_prompt_budget_across_arms",
        "same_tool_budget_across_arms",
        "same_time_budget_across_arms",
        "same_repair_attempt_budget_across_arms",
        "one_evaluation_per_qualified_case_per_arm",
    ):
        _require_true(evaluation.get(field), f"evaluation_policy.{field}")

    primary_endpoint = _require_string(data.get("primary_endpoint"), "primary_endpoint")
    if primary_endpoint != EXPECTED_PRIMARY_ENDPOINT:
        raise ValueError(f"primary_endpoint must be {EXPECTED_PRIMARY_ENDPOINT}")
    primary_endpoint_denominator = _require_string(
        data.get("primary_endpoint_denominator"), "primary_endpoint_denominator"
    )
    if "infrastructure errors are excluded" not in primary_endpoint_denominator:
        raise ValueError("primary endpoint denominator must exclude infrastructure errors explicitly")

    analysis = _require_mapping(data.get("analysis_policy"), "analysis_policy")
    for field in (
        "report_all_arms",
        "report_per_case_outcomes",
        "report_primary_endpoint_before_secondary",
        "report_evaluable_coverage_with_primary_endpoint",
        "no_posthoc_exclusions",
        "no_posthoc_protocol_changes",
        "no_protected_tuning",
    ):
        _require_true(analysis.get(field), f"analysis_policy.{field}")

    stopping_rule = _require_string(data.get("stopping_rule"), "stopping_rule")
    return Checkpoint3CausalProtocol(
        protocol=protocol,
        qualification_protocol=qualification_protocol,
        upstream_commit=upstream_commit,
        arms=arms,
        primary_endpoint=primary_endpoint,
        primary_endpoint_denominator=primary_endpoint_denominator,
        stopping_rule=stopping_rule,
        frozen_before_protected_evaluation=True,
        raw=data,
    )


def load_protocol(path: Path | str) -> Checkpoint3CausalProtocol:
    path = Path(path)
    data = json.loads(path.read_text())
    if not isinstance(data, Mapping):
        raise ValueError("protocol root must be an object")
    return validate_protocol(data)


def default_protocol_path() -> Path:
    return Path(__file__).with_name("CHECKPOINT3_CAUSAL_PROTOCOL_V1.json")


def load_default_protocol() -> Checkpoint3CausalProtocol:
    return load_protocol(default_protocol_path())
