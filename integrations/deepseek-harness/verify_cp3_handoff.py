from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

EXPECTED_BUILD_PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_CAPABILITY_BUILD_V1"
EXPECTED_ACCEPTANCE_PROTOCOL = "TRISKELION_DEEPSEEK_HARNESS_CP3_ACCEPTANCE_V1"
EXPECTED_DEMO_PROTOCOL = "TRISKELION_CP3_DEMO_CASE_SELECTOR_V1"
EXPECTED_HARNESS_COMMIT = "47f943859bef60e4160492346772ded9b24f765a"
EXPECTED_LIFECYCLE = ["install", "disable", "enable", "uninstall"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def canonical_capability_id(capability: Mapping[str, Any]) -> str:
    unsigned = dict(capability)
    unsigned.pop("capability_id", None)
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Independently verify the complete CP3 -> DeepSeek Harness evidence chain.")
    ap.add_argument("--capability", type=Path, required=True)
    ap.add_argument("--build-summary", type=Path, required=True)
    ap.add_argument("--rows", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--demo", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    capability = load(args.capability)
    build = load(args.build_summary)
    rows = load(args.rows)
    results = load(args.results)
    demo = load(args.demo)
    receipt = load(args.receipt)

    require(isinstance(capability, Mapping), "CAPABILITY.json root is not an object")
    require(isinstance(build, Mapping), "BUILD_SUMMARY.json root is not an object")
    require(isinstance(rows, list), "ROWS.json root is not an array")
    require(isinstance(results, Mapping), "RESULTS.json root is not an object")
    require(isinstance(demo, Mapping), "DEMO_CASE.json root is not an object")
    require(isinstance(receipt, Mapping), "RECEIPT.json root is not an object")

    capability_id = capability.get("capability_id")
    require(isinstance(capability_id, str) and len(capability_id) == 64, "invalid capability_id")
    require(canonical_capability_id(capability) == capability_id, "canonical CAPABILITY.json identity mismatch")
    require(build.get("capability_id") == capability_id, "build summary capability identity mismatch")
    require(build.get("build_protocol") == EXPECTED_BUILD_PROTOCOL, "unexpected build protocol")
    require(int(build.get("admitted_rule_count", 0)) >= 1, "no admitted rules")
    require(results.get("capability_id") == capability_id, "protected evaluation capability identity mismatch")
    require(demo.get("capability_id") == capability_id, "demo capability identity mismatch")
    require(receipt.get("capability_id") == capability_id, "receipt capability identity mismatch")
    require(receipt.get("capability_file_sha256") == sha256_file(args.capability), "receipt file SHA-256 mismatch")

    require(demo.get("protocol") == EXPECTED_DEMO_PROTOCOL, "unexpected demo selector protocol")
    require(demo.get("selection_is_posthoc_visualization_only") is True, "demo scientific-scope flag missing")
    require(demo.get("aggregate_result_remains_authoritative") is True, "aggregate-authority flag missing")
    selected = demo.get("selected")
    require(isinstance(selected, Mapping), "no selected causal demo case")
    cold = selected.get("cold")
    verified = selected.get("verified")
    require(isinstance(cold, Mapping) and isinstance(verified, Mapping), "selected arm evidence missing")
    require(cold.get("classification") == "competence", "selected COLD row is not competence evidence")
    require(cold.get("repaired") is False, "selected COLD row did not fail")
    require(verified.get("classification") == "competence", "selected VERIFIED row is not competence evidence")
    require(verified.get("repaired") is True, "selected VERIFIED row did not pass")
    require(verified.get("activated") is True, "selected VERIFIED capability was not activated")
    require(verified.get("false_activation") is False, "selected VERIFIED row is a false activation")
    require(cold.get("project") == selected.get("project") == verified.get("project"), "selected project mismatch")
    require(str(cold.get("bug_id")) == str(selected.get("bug_id")) == str(verified.get("bug_id")), "selected bug mismatch")

    case_key = (str(selected.get("project")), str(selected.get("bug_id")))
    grouped = [r for r in rows if (str(r.get("project")), str(r.get("bug_id"))) == case_key]
    require(len(grouped) == 4, "selected case does not have exactly four protected arm rows")
    by_arm = {str(r.get("arm")): r for r in grouped}
    require(set(by_arm) == {"cold", "raw_memory", "always_on", "verified"}, "selected case arm matrix is incomplete")
    require(by_arm["cold"] == cold, "selected COLD evidence does not exactly match ROWS.json")
    require(by_arm["verified"] == verified, "selected VERIFIED evidence does not exactly match ROWS.json")

    require(receipt.get("protocol") == EXPECTED_ACCEPTANCE_PROTOCOL, "unexpected acceptance protocol")
    require(receipt.get("result") == "PASS", "Harness lifecycle receipt is not PASS")
    require(receipt.get("harness_commit") == EXPECTED_HARNESS_COMMIT, "Harness commit drift")
    require(receipt.get("lifecycle") == EXPECTED_LIFECYCLE, "Harness lifecycle drift")
    handoff_commit = current_commit()
    require(receipt.get("handoff_code_commit") == handoff_commit, "handoff code commit mismatch")
    receipt_demo = receipt.get("demo_case")
    require(isinstance(receipt_demo, Mapping), "receipt demo pointer missing")
    require(str(receipt_demo.get("project")) == str(selected.get("project")), "receipt project mismatch")
    require(str(receipt_demo.get("bug_id")) == str(selected.get("bug_id")), "receipt bug mismatch")
    require(int(receipt_demo.get("frozen_case_index")) == int(selected.get("frozen_case_index")), "receipt frozen case index mismatch")

    row_count = results.get("row_count")
    protected_count = results.get("protected_case_count")
    require(isinstance(row_count, int) and isinstance(protected_count, int), "protected result counts missing")
    require(row_count == protected_count * 4 == len(rows), "protected four-arm result matrix is incomplete")

    verification = {
        "protocol": "TRISKELION_CP3_DEEPSEEK_HANDOFF_VERIFICATION_V1",
        "result": "PASS",
        "capability_id": capability_id,
        "capability_file_sha256": sha256_file(args.capability),
        "admitted_rule_count": int(build["admitted_rule_count"]),
        "protected_case_count": protected_count,
        "protected_row_count": row_count,
        "handoff_code_commit": handoff_commit,
        "harness_commit": EXPECTED_HARNESS_COMMIT,
        "lifecycle": EXPECTED_LIFECYCLE,
        "demo_case": {
            "frozen_case_index": int(selected["frozen_case_index"]),
            "project": str(selected["project"]),
            "bug_id": str(selected["bug_id"]),
            "cold_repaired": False,
            "verified_repaired": True,
            "verified_activated": True,
            "verified_false_activation": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n")
    print(json.dumps(verification, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
