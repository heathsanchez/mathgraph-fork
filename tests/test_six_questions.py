"""Six distinct obligations over admitted finite source-to-decision records."""

from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from math import nan
import subprocess
import sys

from research.gap_conditional_cell.six_questions import (
    audit_frozen_cases, evaluate_case, naive_equality_baseline,
)
from research.gap_conditional_cell.structural import canonical, read_cases


def _case():
    return {
        "id": "two-filter-replay",
        "authority": "declared",
        "complete": True,
        "rows": [
            {"input": {"filter": "off"}, "old_image": 7, "target": 0},
            {"input": {"filter": "on"}, "old_image": 7, "target": 1},
        ],
    }


def test_distinguishes_consequential_collision_from_type_and_authority_warrants():
    # Fails if a collision becomes global correctness or repair authorization.
    report = evaluate_case(_case(), input_types={"filter": "string"}, old_type="integer")

    assert report["checks"]["type_correctness"] == "RECORDED_TYPES_CONFORM"
    assert report["checks"]["interface_correctness"] == "COUNTEREXAMPLE_CONDITIONAL"
    assert report["checks"]["meaning_gap"] == "CONSEQUENTIAL_COLLISION"
    assert report["checks"]["specification_adequacy"] == "DECLARED_CONTRACT_ONLY"
    assert report["checks"]["evidence_gap"] == "UNKNOWN_SOURCE_REPLAY"
    assert report["checks"]["authority_gap"] == "NO_CHANGE_PERMISSION"
    assert report["verdict"] == "CANDIDATE_UNREPLAYED"
    assert report["witness"]["different_required_outcomes"] is True
    assert report["may_change"] is False


def test_benign_merge_is_not_a_gap():
    # Fails if a generic hash collision is automatically treated as harmful.
    case = _case()
    case["rows"][1]["target"] = 0
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")

    assert report["checks"]["interface_correctness"] == "NO_GAP_FROZEN_FINITE"
    assert report["checks"]["meaning_gap"] == "NO_CONSEQUENTIAL_COLLISION"
    assert report["witness"] is None
    assert report["verdict"] == "UNKNOWN_SOURCE_REPLAY"


def test_false_split_without_behavioral_dependency_is_not_a_gap():
    case = _case()
    case["rows"][1]["old_image"] = 8
    case["rows"][1]["target"] = 0
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["meaning_gap"] == "NO_CONSEQUENTIAL_COLLISION"


def test_missing_type_contract_is_unknown_not_type_sound():
    report = evaluate_case(_case())
    assert report["checks"]["type_correctness"] == "UNKNOWN_TYPE_CONTRACT"
    assert report["verdict"] == "CANDIDATE_TYPE_UNKNOWN"


def test_bool_does_not_satisfy_integer_contract():
    case = _case()
    case["rows"][0]["old_image"] = True
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["type_correctness"] == "TYPE_MISMATCH"
    assert report["verdict"] == "REJECTED_INVALID_PREMISE"


def test_missing_owner_intent_blocks_promotion_without_erasing_witness():
    case = _case()
    case["authority"] = "unknown"
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["specification_adequacy"] == "UNKNOWN_OWNER_INTENT"
    assert report["checks"]["meaning_gap"] == "UNRATIFIED_COLLISION"
    assert report["verdict"] == "CANDIDATE_REQUIREMENT_UNRATIFIED"
    assert report["may_change"] is False


def test_incomplete_no_gap_remains_unknown():
    case = _case()
    case["rows"][1]["old_image"] = 8
    case["complete"] = False
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["interface_correctness"] == "UNKNOWN_INCOMPLETE_DOMAIN"
    assert report["verdict"] == "UNKNOWN_INCOMPLETE_DOMAIN"


def test_source_identical_but_required_outcomes_differ_is_unobservable():
    case = deepcopy(_case())
    case["rows"][1]["input"] = deepcopy(case["rows"][0]["input"])
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["interface_correctness"] == "SOURCE_NONIDENTIFIABLE"
    assert report["verdict"] == "UNKNOWN_NEEDS_NEW_OBSERVATION"
    assert report["may_change"] is False


def test_source_digest_and_replay_admit_only_conditional_bounded_witness():
    source = b"frozen original source bytes"
    report = evaluate_case(
        _case(), input_types={"filter": "string"}, old_type="integer",
        source_bytes=source, source_sha256=sha256(source).hexdigest(),
        replay=lambda original: 7,
    )
    assert report["checks"]["evidence_gap"] == "DECLARED_BYTES_AND_REPLAY_MATCH"
    assert report["verdict"] == "WARRANTED_BOUNDED_CONDITIONAL_RELATION"
    assert report["may_change"] is False
    assert "caller" in report["limitations"][0].lower()


def test_changed_source_bytes_cannot_inherit_old_warrant():
    original = b"frozen original source bytes"
    report = evaluate_case(
        _case(), input_types={"filter": "string"}, old_type="integer",
        source_bytes=original + b"changed", source_sha256=sha256(original).hexdigest(),
        replay=lambda original: 7,
    )
    assert report["checks"]["evidence_gap"] == "SOURCE_DIGEST_MISMATCH"
    assert report["verdict"] == "REJECTED_EVIDENCE_DRIFT"
    assert report["may_change"] is False


def test_replay_divergence_cannot_be_hidden_by_valid_source_hash():
    source = b"frozen original source bytes"
    report = evaluate_case(
        _case(), input_types={"filter": "string"}, old_type="integer",
        source_bytes=source, source_sha256=sha256(source).hexdigest(),
        replay=lambda original: 8,
    )
    assert report["checks"]["evidence_gap"] == "REPLAY_MISMATCH"
    assert report["verdict"] == "REJECTED_REPLAY_MISMATCH"


def test_unavailable_replay_and_source_are_unknown_not_warranted():
    source = b"frozen original source bytes"
    report = evaluate_case(
        _case(), input_types={"filter": "string"}, old_type="integer",
        source_sha256=sha256(source).hexdigest(), replay=lambda original: 7,
    )
    assert report["checks"]["evidence_gap"] == "UNKNOWN_SOURCE_REPLAY"
    assert report["verdict"] == "CANDIDATE_UNREPLAYED"


def test_replay_failure_yields_unknown_not_a_defect():
    source = b"frozen original source bytes"

    def broken_replay(original):
        raise RuntimeError("external test runner unavailable")

    report = evaluate_case(
        _case(), input_types={"filter": "string"}, old_type="integer",
        source_bytes=source, source_sha256=sha256(source).hexdigest(),
        replay=broken_replay,
    )
    assert report["checks"]["evidence_gap"] == "UNKNOWN_REPLAY_FAILURE"
    assert report["verdict"] == "UNKNOWN_REPLAY_FAILURE"


def test_existing_frozen_multi_project_cases_remain_bounded():
    # A classifier must not rewrite original cases or convert their lessons
    # into unqualified claims about the original repositories.
    audit = audit_frozen_cases()
    assert audit["structural_counts"] == {
        "ELIGIBLE_GAP": 5,
        "SUFFICIENT_FROZEN_FINITE": 1,
        "UNKNOWN_INCOMPLETE": 1,
        "UNKNOWN_AUTHORITY": 1,
        "UNOBSERVABLE_FROM_SOURCE": 1,
    }
    assert len(audit["reports"]) == 9
    assert all(not r["may_change"] for r in audit["reports"])
    assert all(not r["verdict"].startswith("WARRANTED_") for r in audit["reports"])
    assert "not source-native" in audit["scope"]


def test_naive_collision_baseline_raises_a_false_alarm_on_safe_quotient():
    harmless = _case()
    harmless["rows"][1]["target"] = 0
    assert naive_equality_baseline(harmless) is True
    assert evaluate_case(harmless, input_types={"filter": "string"}, old_type="integer")[
        "checks"]["meaning_gap"] == "NO_CONSEQUENTIAL_COLLISION"


def test_frozen_audit_has_replayable_json_cli_without_external_calls():
    cmd = [sys.executable, "-m", "research.gap_conditional_cell.six_questions", "--frozen"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    record = json.loads(result.stdout)
    assert record["structural_counts"]["ELIGIBLE_GAP"] == 5
    assert record["replay_calls"] == 0


def test_empty_or_malformed_rows_fail_closed():
    empty = _case()
    empty["rows"] = []
    assert evaluate_case(empty, input_types={"filter": "string"}, old_type="integer")[
        "verdict"] == "UNKNOWN_EMPTY_DOMAIN"
    missing = _case()
    del missing["rows"][0]["old_image"]
    assert evaluate_case(missing, input_types={"filter": "string"}, old_type="integer")[
        "verdict"] == "REJECTED_INVALID_PREMISE"


def test_nonfinite_numeric_observation_is_not_json_type_valid():
    case = _case()
    case["rows"][0]["old_image"] = nan
    assert evaluate_case(case, input_types={"filter": "string"}, old_type="number")[
        "verdict"] == "REJECTED_INVALID_PREMISE"


def test_same_source_input_with_different_observation_needs_state_or_time():
    case = _case()
    case["rows"][1]["input"] = deepcopy(case["rows"][0]["input"])
    case["rows"][1]["old_image"] = 8
    case["rows"][1]["target"] = 0
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["interface_correctness"] == "UNKNOWN_NONFUNCTIONAL_SOURCE"
    assert report["verdict"] == "UNKNOWN_NEEDS_STATE_OR_TIME"


def test_source_target_contradiction_outweighs_earlier_nondeterministic_observation():
    case = _case()
    case["rows"] = [
        {"input": {"filter": "off"}, "old_image": 7, "target": 0},
        {"input": {"filter": "off"}, "old_image": 8, "target": 0},
        {"input": {"filter": "off"}, "old_image": 8, "target": 1},
    ]
    report = evaluate_case(case, input_types={"filter": "string"}, old_type="integer")
    assert report["checks"]["interface_correctness"] == "SOURCE_NONIDENTIFIABLE"
    assert report["verdict"] == "UNKNOWN_NEEDS_NEW_OBSERVATION"


def test_all_256_small_finite_relations_match_independent_pairwise_oracle():
    # Literal independent oracle: an unsafe merge exists iff some pair has
    # equal projected observations and different protected decisions.
    for bits in product((0, 1), repeat=8):
        old, targets = bits[:4], bits[4:]
        case = {
            "id": "four-state-exhaustive", "authority": "declared", "complete": True,
            "rows": [
                {"input": {"state": i}, "old_image": old[i], "target": targets[i]}
                for i in range(4)
            ],
        }
        oracle = any(old[i] == old[j] and targets[i] != targets[j]
                     for i in range(4) for j in range(i+1, 4))
        result = evaluate_case(case, input_types={"state": "integer"}, old_type="integer")
        assert (result["checks"]["meaning_gap"] == "CONSEQUENTIAL_COLLISION") == oracle
        assert (result["witness"] is not None) == oracle
        assert result["may_change"] is False


def test_fully_informed_independent_pairwise_baseline_ties_on_frozen_collisions():
    # A conventional reviewer with the SAME target labels can use this
    # elementary O(n^2) test. We must not claim unique discovery value.
    cases = read_cases()["cases"]
    considered = 0
    baseline_positives = 0
    gate_positives = 0
    for case in cases:
        if case["authority"] != "declared":
            continue
        rows = case["rows"]
        if any(canonical(x["input"]) == canonical(y["input"])
               and canonical(x["target"]) != canonical(y["target"])
               for i, x in enumerate(rows) for y in rows[i+1:]):
            continue  # Impossible from those source fields, not a repair win.
        expected = any(canonical(x["old_image"]) == canonical(y["old_image"])
                       and canonical(x["target"]) != canonical(y["target"])
                       for i, x in enumerate(rows) for y in rows[i+1:])
        actual = evaluate_case(case)["checks"]["interface_correctness"] == "COUNTEREXAMPLE_CONDITIONAL"
        assert actual == expected
        considered += 1
        baseline_positives += expected
        gate_positives += actual
    assert (considered, baseline_positives, gate_positives) == (7, 5, 5)
