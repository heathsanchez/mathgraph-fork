"""Six independent checks over admitted finite source-to-decision records.

This cannot independently authenticate requirements or source/target oracle
rows. A witness is always conditional on those declared rows and their scope.
"""

from research.gap_conditional_cell.structural import assess, canonical, read_cases, source_digest

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json


JSON_TYPES = {
    "string": lambda v: type(v) is str,
    "integer": lambda v: type(v) is int,
    "number": lambda v: type(v) in (int, float),
    "boolean": lambda v: type(v) is bool,
    "array": lambda v: type(v) is list,
    "object": lambda v: type(v) is dict,
    "null": lambda v: v is None,
}


def _preflight(case):
    if not isinstance(case, dict) or not isinstance(case.get("rows"), list):
        return "INVALID"
    rows = case["rows"]
    if not rows:
        return "EMPTY"
    source_observations = {}
    source_target_conflict = False
    nonfunctional_observation = False
    for row in rows:
        if not isinstance(row, dict) or not {"input", "old_image", "target"} <= row.keys():
            return "INVALID"
        try:
            src, old, target = (canonical(row[field]) for field in ("input", "old_image", "target"))
        except (ValueError, TypeError, OverflowError, RecursionError):
            return "INVALID"
        if src in source_observations:
            prev_old, prev_target = source_observations[src]
            source_target_conflict |= prev_target != target
            nonfunctional_observation |= prev_old != old
        source_observations.setdefault(src, (old, target))
    if source_target_conflict:
        return "VALID"  # Structural gate reports the stronger impossibility.
    if nonfunctional_observation:
        return "NONFUNCTIONAL"
    return "VALID"


def _type_status(case, input_types, old_type):
    if input_types is None or old_type is None:
        return "UNKNOWN_TYPE_CONTRACT"
    if (not isinstance(input_types, dict) or
            any(kind not in JSON_TYPES for kind in input_types.values()) or
            old_type not in JSON_TYPES):
        return "UNKNOWN_TYPE_CONTRACT"
    for row in case.get("rows", []):
        source = row.get("input")
        if (not isinstance(source, dict) or set(source) != set(input_types) or
                any(not JSON_TYPES[kind](source[name])
                    for name, kind in input_types.items()) or
                not JSON_TYPES[old_type](row.get("old_image"))):
            return "TYPE_MISMATCH"
    return "RECORDED_TYPES_CONFORM"


def _evidence_status(case, source_bytes, source_sha256, replay):
    """Check supplied bytes and callback behavior, not callback provenance."""
    if source_bytes is None or source_sha256 is None or replay is None:
        return "UNKNOWN_SOURCE_REPLAY"
    if (not isinstance(source_bytes, bytes) or not isinstance(source_sha256, str)
            or sha256(source_bytes).hexdigest() != source_sha256):
        return "SOURCE_DIGEST_MISMATCH"
    try:
        for row in case["rows"]:
            # Do not let a callback mutate our declared source state or labels.
            actual = replay(deepcopy(row["input"]))
            if canonical(actual) != canonical(row["old_image"]):
                return "REPLAY_MISMATCH"
    except Exception:
        return "UNKNOWN_REPLAY_FAILURE"
    return "DECLARED_BYTES_AND_REPLAY_MATCH"


def evaluate_case(case, *, input_types=None, old_type=None, source_bytes=None,
                  source_sha256=None, replay=None):
    """Return an admission-bound, six-question report; never grant a change."""
    preflight = _preflight(case)
    if preflight != "VALID":
        interface = ("UNKNOWN_NONFUNCTIONAL_SOURCE" if preflight == "NONFUNCTIONAL"
                     else "UNKNOWN_EMPTY_DOMAIN" if preflight == "EMPTY"
                     else "UNKNOWN_INVALID_PREMISE")
        verdict = ("UNKNOWN_NEEDS_STATE_OR_TIME" if preflight == "NONFUNCTIONAL"
                   else "UNKNOWN_EMPTY_DOMAIN" if preflight == "EMPTY"
                   else "REJECTED_INVALID_PREMISE")
        return {
            "case_id": case.get("id") if isinstance(case, dict) else None,
            "checks": {
                "type_correctness": "UNKNOWN_PREMISE",
                "interface_correctness": interface,
                "specification_adequacy": "UNKNOWN_PREMISE",
                "meaning_gap": "UNKNOWN_MEANING",
                "evidence_gap": "UNKNOWN_SOURCE_REPLAY",
                "authority_gap": "NO_CHANGE_PERMISSION",
            },
            "witness": None, "verdict": verdict, "may_change": False,
            "limitations": ["Invalid, empty or nonfunctional source observations cannot justify a decision."],
        }
    type_status = _type_status(case, input_types, old_type)
    evidence_status = _evidence_status(case, source_bytes, source_sha256, replay)
    # Existing structural gate rejects unratified authority up front. For a
    # *candidate* diagnostic we may still expose an algebraic collision, but
    # must never promote it as a requirement violation without authority.
    core = assess({**case, "authority": "declared"})
    structural = core["status"]
    owner_declared = case.get("authority") == "declared"
    interface = {
        "ELIGIBLE_GAP": "COUNTEREXAMPLE_CONDITIONAL",
        "SUFFICIENT_FROZEN_FINITE": "NO_GAP_FROZEN_FINITE",
        "UNKNOWN_INCOMPLETE": "UNKNOWN_INCOMPLETE_DOMAIN",
        "UNOBSERVABLE_FROM_SOURCE": "SOURCE_NONIDENTIFIABLE",
        "UNKNOWN_TARGET": "UNKNOWN_TARGET",
    }.get(structural, "UNKNOWN_INVALID_PREMISE")
    meaning = (
        ("CONSEQUENTIAL_COLLISION" if owner_declared else "UNRATIFIED_COLLISION")
        if structural == "ELIGIBLE_GAP"
        else "NO_CONSEQUENTIAL_COLLISION" if structural == "SUFFICIENT_FROZEN_FINITE"
        else "UNKNOWN_MEANING"
    )
    if evidence_status == "SOURCE_DIGEST_MISMATCH":
        verdict = "REJECTED_EVIDENCE_DRIFT"
    elif evidence_status == "REPLAY_MISMATCH":
        verdict = "REJECTED_REPLAY_MISMATCH"
    elif evidence_status == "UNKNOWN_REPLAY_FAILURE":
        verdict = "UNKNOWN_REPLAY_FAILURE"
    elif type_status == "TYPE_MISMATCH":
        verdict = "REJECTED_INVALID_PREMISE"
    elif structural == "UNOBSERVABLE_FROM_SOURCE":
        verdict = "UNKNOWN_NEEDS_NEW_OBSERVATION"
    elif structural == "UNKNOWN_INCOMPLETE":
        verdict = "UNKNOWN_INCOMPLETE_DOMAIN"
    elif not owner_declared:
        verdict = "CANDIDATE_REQUIREMENT_UNRATIFIED" if structural == "ELIGIBLE_GAP" else "UNKNOWN_OWNER_INTENT"
    elif type_status != "RECORDED_TYPES_CONFORM":
        verdict = "CANDIDATE_TYPE_UNKNOWN" if structural == "ELIGIBLE_GAP" else "UNKNOWN_TYPE_CONTRACT"
    elif structural == "ELIGIBLE_GAP":
        verdict = ("WARRANTED_BOUNDED_CONDITIONAL_RELATION"
                   if evidence_status == "DECLARED_BYTES_AND_REPLAY_MATCH"
                   else "CANDIDATE_UNREPLAYED")
    else:
        verdict = ("NO_GAP_IN_FROZEN_FINITE"
                   if structural == "SUFFICIENT_FROZEN_FINITE"
                   and evidence_status == "DECLARED_BYTES_AND_REPLAY_MATCH"
                   else "UNKNOWN_SOURCE_REPLAY")

    return {
        "case_id": case.get("id"),
        "checks": {
            "type_correctness": type_status,
            "interface_correctness": interface,
            "specification_adequacy": "DECLARED_CONTRACT_ONLY" if owner_declared else "UNKNOWN_OWNER_INTENT",
            "meaning_gap": meaning,
            "evidence_gap": evidence_status,
            "authority_gap": "NO_CHANGE_PERMISSION",
        },
        "witness": core["witness"],
        "verdict": verdict,
        "may_change": False,
        "limitations": [
            "Caller-provided source bytes, replay code and target labels are not independently authenticated by this evaluator.",
            "A finite relation or counterexample is conditional on admitted inputs, declared targets and exact replay behavior.",
            "Engineering intent, upstream deployment behavior and change authorization remain outside this gate.",
        ],
    }


def naive_equality_baseline(case):
    """Weak identity-only baseline: flags even decision-irrelevant merges."""
    seen = {}
    for row in case["rows"]:
        key = canonical(row["old_image"])
        if key in seen and seen[key] != canonical(row["input"]):
            return True
        seen[key] = canonical(row["input"])
    return False


def audit_frozen_cases():
    """Read existing immutable research fixtures; never manufacture source replay."""
    data = read_cases()
    cases = data["cases"]
    return {
        "schema": "mathgraph/six-question-audit-v1",
        "frozen_cases_sha256": source_digest(),
        "scope": "Retrospective finite research fixtures, not source-native upstream replays or an independent owner-intent study.",
        "structural_counts": dict(sorted(Counter(assess(c)["status"] for c in cases).items())),
        "naive_identity_alerts": sum(naive_equality_baseline(c) for c in cases),
        "replay_calls": 0,
        "reports": [evaluate_case(c) for c in cases],
    }


def main():
    parser = argparse.ArgumentParser(description="Bounded six-question finite research audit")
    parser.add_argument("--frozen", action="store_true", required=True,
                        help="read only the immutable nine-case research fixture")
    args = parser.parse_args()
    if args.frozen:
        print(json.dumps(audit_frozen_cases(), sort_keys=True, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
