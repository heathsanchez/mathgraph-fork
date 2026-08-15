from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

ARMS = ("cold", "raw_memory", "always_on", "verified")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Select the first frozen protected case showing COLD fail -> VERIFIED pass. "
            "This is a deterministic visualization selector, not a replacement for aggregate evaluation."
        )
    )
    ap.add_argument("--rows", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--capability", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows = json.loads(args.rows.read_text())
    results = json.loads(args.results.read_text())
    capability = json.loads(args.capability.read_text())
    require(isinstance(rows, list), "ROWS.json must contain an array")
    require(isinstance(results, Mapping), "RESULTS.json must contain an object")
    require(isinstance(capability, Mapping), "CAPABILITY.json must contain an object")
    require(results.get("capability_id") == capability.get("capability_id"), "capability identity mismatch")

    by_case: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}
    order: list[tuple[str, str]] = []
    for raw in rows:
        require(isinstance(raw, Mapping), "row must be an object")
        key = (str(raw.get("project", "")), str(raw.get("bug_id", "")))
        arm = str(raw.get("arm", ""))
        require(all(key) and arm in ARMS, "invalid protected row identity")
        if key not in by_case:
            by_case[key] = {}
            order.append(key)
        require(arm not in by_case[key], f"duplicate arm for {key}")
        by_case[key][arm] = raw

    selected = None
    for index, key in enumerate(order):
        arm_rows = by_case[key]
        if set(arm_rows) != set(ARMS):
            continue
        cold = arm_rows["cold"]
        verified = arm_rows["verified"]
        if (
            cold.get("classification") == "competence"
            and verified.get("classification") == "competence"
            and cold.get("repaired") is False
            and verified.get("repaired") is True
            and verified.get("activated") is True
            and verified.get("false_activation") is False
        ):
            selected = {
                "frozen_case_index": index,
                "project": key[0],
                "bug_id": key[1],
                "cold": dict(cold),
                "verified": dict(verified),
            }
            break

    verified_summary = results.get("summary", {}).get("verified", {})
    cold_summary = results.get("summary", {}).get("cold", {})
    manifest = {
        "protocol": "TRISKELION_CP3_DEMO_CASE_SELECTOR_V1",
        "selection_rule": (
            "first case in frozen ROWS order where COLD is evaluable+fails, VERIFIED is "
            "evaluable+passes, VERIFIED activated, and VERIFIED false_activation is false"
        ),
        "selection_is_posthoc_visualization_only": True,
        "aggregate_result_remains_authoritative": True,
        "capability_id": capability.get("capability_id"),
        "cold_aggregate": cold_summary,
        "verified_aggregate": verified_summary,
        "selected": selected,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))

    if selected is None:
        raise SystemExit(
            "no protected COLD-fail/VERIFIED-pass causal demo case exists; refusing to manufacture one"
        )


if __name__ == "__main__":
    main()
