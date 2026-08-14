from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ARMS = ("cold", "raw_memory", "always_on", "verified", "wrong_scope_manifest")


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [max(0.0, center - half), min(1.0, center + half)]


def difference_interval(a_k: int, a_n: int, b_k: int, b_n: int) -> dict:
    a = wilson(a_k, a_n); b = wilson(b_k, b_n)
    return {"estimate": a_k / a_n - b_k / b_n,
            "newcombe_95": [max(-1.0, a[0] - b[1]), min(1.0, a[1] - b[0])]}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--inputs", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists(): raise SystemExit("output exists; refusing to overwrite")
    summaries = {}
    calls = {}
    for arm in ARMS:
        matches = [p for p in args.inputs.rglob("RESULTS.json") if p.parent.name == arm or p.parent.name.endswith("-" + arm)]
        if len(matches) != 1: raise SystemExit(f"expected one result for {arm}, found {matches}")
        root = matches[0].parent
        summaries[arm] = json.loads(matches[0].read_text())
        calls[arm] = json.loads((root / "RAW" / "calls.json").read_text())
    task_orders = [[x["task_id"] for x in calls[a]] for a in ARMS]
    if any(order != task_orders[0] for order in task_orders[1:]):
        raise SystemExit("arm task orders differ")
    task_count = len(task_orders[0])
    for arm in ARMS:
        summaries[arm]["success_wilson_95"] = wilson(summaries[arm]["passed"], summaries[arm]["total"])
        summaries[arm]["false_activation_wilson_95"] = wilson(
            summaries[arm]["false_activations"], summaries[arm]["selected_activations"])
    success_delta = difference_interval(summaries["verified"]["passed"], task_count,
                                        summaries["cold"]["passed"], task_count)
    fa_delta = difference_interval(summaries["always_on"]["false_activations"],
                                   summaries["always_on"]["selected_activations"],
                                   summaries["verified"]["false_activations"],
                                   summaries["verified"]["selected_activations"])
    result = {"protocol": "TRISKELION_QUIXBUGS_SCALE_V1", "arms": summaries,
              "task_order": task_orders[0],
              "deltas": {"verified_minus_cold_success": success_delta,
                         "always_on_minus_verified_false_activation": fa_delta},
              "gates": {
                  "complete_35_by_5": all(summaries[a]["total"] == 35 for a in ARMS),
                  "zero_infrastructure_errors": sum(summaries[a]["infrastructure_errors"] for a in ARMS) == 0,
                  "verified_success_gt_cold": success_delta["estimate"] > 0,
                  "verified_success_gt_always_on": summaries["verified"]["passed"] > summaries["always_on"]["passed"],
                  "verified_false_activation_lt_always_on": fa_delta["estimate"] > 0,
                  "wrong_scope_harms_vs_verified": summaries["wrong_scope_manifest"]["passed"] < summaries["verified"]["passed"],
              }}
    args.out.mkdir(parents=True)
    (args.out / "RESULTS.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (args.out / "RAW_POINTERS.json").write_text(json.dumps({a: str(args.inputs) for a in ARMS}, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__": main()
