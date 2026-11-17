#!/usr/bin/env python3
"""Independent, no-secret scoring of frozen choice/abstention decisions."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    cases_bytes = (HERE / "cases.json").read_bytes()
    cases_obj = json.loads(cases_bytes)
    results = json.loads((HERE / "results.json").read_text())
    assert results["cases_sha256"] == hashlib.sha256(cases_bytes).hexdigest(), "DATASET_DRIFT"
    arms = cases_obj["arms"]
    expected_keys = {(x["id"], arm) for x in cases_obj["cases"] for arm in arms}
    actual_keys = [(x["case_id"], x["arm"]) for x in results["calls"]]
    assert len(actual_keys) == len(set(actual_keys)), "DUPLICATE_CALL"
    assert set(actual_keys).issubset(expected_keys), "UNKNOWN_CASE_OR_ARM"
    answers = {(x["case_id"], x["arm"]): x for x in results["calls"]}
    details = []
    for case in cases_obj["cases"]:
        for arm in arms:
            r = answers.get((case["id"], arm), {})
            choice = r.get("choice")
            status = r.get("status", "MISSING")
            details.append({
                "id": case["id"], "category": case["category"], "source": case["source"],
                "arm": arm, "correct_label": case["correct"], "selected": choice,
                "status": status, "correct": choice == case["correct"],
                "false_accusation": case["category"] == "contract_unknown" and choice in "ABCD"
                if isinstance(choice, str) else False,
                "unsupported_abstention": case["category"] == "external_merged" and choice == "E",
            })
    per_arm = {}
    for arm in arms:
        rows = [x for x in details if x["arm"] == arm]
        per_arm[arm] = {
            "correct": sum(x["correct"] for x in rows),
            "n": len(rows),
            "merged_repair_correct": sum(x["correct"] for x in rows if x["category"] == "external_merged"),
            "merged_repair_n": sum(x["category"] == "external_merged" for x in rows),
            "unknown_correct_abstain": sum(x["correct"] for x in rows if x["category"] == "contract_unknown"),
            "unknown_n": sum(x["category"] == "contract_unknown" for x in rows),
            "false_accusations": sum(x["false_accusation"] for x in rows),
            "unsupported_abstentions": sum(x["unsupported_abstention"] for x in rows),
            "invalid_or_missing": sum(x["status"] not in ("RESPONSE",) for x in rows),
        }
    pairs = []
    for case in cases_obj["cases"]:
        row = {arm: answers.get((case["id"], arm), {}).get("choice") for arm in arms}
        pairs.append({
            "id": case["id"], "reference": case["correct"], **row,
            "diagnostic_changed_raw": row["DISTINCTION"] != row["RAW"],
            "diagnostic_corrected_raw": row["RAW"] != case["correct"] and row["DISTINCTION"] == case["correct"],
            "diagnostic_harmed_raw": row["RAW"] == case["correct"] and row["DISTINCTION"] != case["correct"],
        })
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for r in results["calls"]:
        u = r.get("usage") or {}
        for k in total_usage:
            total_usage[k] += int(u.get(k, 0) or 0)
    completed = (len(results["calls"]) == len(expected_keys)
                 and all(x["status"] == "RESPONSE" for x in results["calls"]))
    summary = {
        "schema": "repair_selection_pilot_results_v1",
        "completed": completed, "source_sha": results["experiment_sha"],
        "cases_sha256": results["cases_sha256"],
        "model_requested": results["model_requested"],
        "model_returned": sorted(set(r.get("model_returned") for r in results["calls"] if r.get("model_returned"))),
        "total_usage": total_usage,
        "counts": per_arm, "paired": pairs,
        "limits": [
            "Eight historical merged PRs and two unratified-contract controls; not random or independent future tasks.",
            "Candidate fixes are prewritten; this tests choice/abstention, not source patch synthesis.",
            "Reference choices are researcher-curated from merged PRs, not fresh human adjudication or native re-execution.",
            "All cases come from published research contexts; model training contamination is unknown.",
            "A passed selection does not establish a generated repair or general ability.",
            "This is a finite pilot without confidence intervals or a general superiority claim.",
        ],
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"completed": completed, "model": summary["model_returned"],
                      "usage": total_usage, "counts": per_arm,
                      "paired_delta": {
                          "corrected": sum(p["diagnostic_corrected_raw"] for p in pairs),
                          "harmed": sum(p["diagnostic_harmed_raw"] for p in pairs),
                      }}, indent=2, sort_keys=True))
    if not completed:
        raise SystemExit("INCOMPLETE_NOT_SCORED_AS_SUCCESS")


if __name__ == "__main__":
    main()
