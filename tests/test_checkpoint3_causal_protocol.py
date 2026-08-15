from __future__ import annotations

import copy

import pytest

from triskelion_runtime.checkpoint3_causal_protocol import (
    EXPECTED_ARMS,
    EXPECTED_PRIMARY_ENDPOINT,
    load_default_protocol,
    validate_protocol,
)


def test_default_checkpoint3_causal_protocol_is_frozen_and_valid() -> None:
    protocol = load_default_protocol()

    assert protocol.arms == EXPECTED_ARMS
    assert protocol.primary_endpoint == EXPECTED_PRIMARY_ENDPOINT
    assert protocol.frozen_before_protected_evaluation is True
    assert protocol.raw["acquisition_policy"]["protected_source_access"] == "forbidden"
    assert protocol.raw["analysis_policy"]["no_protected_tuning"] is True


def test_protocol_rejects_arm_drift() -> None:
    protocol = load_default_protocol()
    changed = copy.deepcopy(dict(protocol.raw))
    changed["arms"] = ["cold", "verified"]

    with pytest.raises(ValueError, match="arms must be exactly"):
        validate_protocol(changed)


def test_protocol_rejects_protected_access_during_capability_building() -> None:
    protocol = load_default_protocol()
    changed = copy.deepcopy(dict(protocol.raw))
    changed["acquisition_policy"]["protected_source_access"] = "allowed"

    with pytest.raises(ValueError, match="protected source access must be forbidden"):
        validate_protocol(changed)


def test_protocol_rejects_hidden_budget_drift() -> None:
    protocol = load_default_protocol()
    changed = copy.deepcopy(dict(protocol.raw))
    changed["evaluation_policy"]["same_repair_attempt_budget_across_arms"] = False

    with pytest.raises(ValueError, match="same_repair_attempt_budget_across_arms"):
        validate_protocol(changed)


def test_protocol_rejects_posthoc_tuning() -> None:
    protocol = load_default_protocol()
    changed = copy.deepcopy(dict(protocol.raw))
    changed["analysis_policy"]["no_protected_tuning"] = False

    with pytest.raises(ValueError, match="no_protected_tuning"):
        validate_protocol(changed)
