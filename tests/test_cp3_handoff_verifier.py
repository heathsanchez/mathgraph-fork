from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def canonical_id(payload: dict) -> str:
    unsigned = dict(payload)
    unsigned.pop("capability_id", None)
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def fixture(tmp_path: Path) -> dict[str, Path]:
    capability = {
        "build_protocol": "TRISKELION_BUGSINPY_CHECKPOINT3_CAPABILITY_BUILD_V1",
        "rules": [{
            "rule_id": "r1",
            "title": "fixture",
            "required_any": ["needle"],
            "required_all": [],
            "forbidden_any": [],
            "repair_instruction": "fixture",
        }],
    }
    capability["capability_id"] = canonical_id(capability)
    cap_path = tmp_path / "CAPABILITY.json"
    write(cap_path, capability)

    build = {
        "build_protocol": "TRISKELION_BUGSINPY_CHECKPOINT3_CAPABILITY_BUILD_V1",
        "capability_id": capability["capability_id"],
        "admitted_rule_count": 1,
    }
    write(tmp_path / "BUILD_SUMMARY.json", build)

    common = {"project": "fixture-project", "bug_id": "1", "classification": "competence"}
    cold = {**common, "arm": "cold", "repaired": False, "activated": False, "false_activation": False}
    raw = {**common, "arm": "raw_memory", "repaired": False, "activated": False, "false_activation": False}
    always = {**common, "arm": "always_on", "repaired": False, "activated": True, "false_activation": True}
    verified = {**common, "arm": "verified", "repaired": True, "activated": True, "false_activation": False}
    rows = [cold, raw, always, verified]
    write(tmp_path / "ROWS.json", rows)
    write(tmp_path / "RESULTS.json", {
        "capability_id": capability["capability_id"],
        "protected_case_count": 1,
        "row_count": 4,
        "summary": {},
    })
    demo = {
        "protocol": "TRISKELION_CP3_DEMO_CASE_SELECTOR_V1",
        "selection_is_posthoc_visualization_only": True,
        "aggregate_result_remains_authoritative": True,
        "capability_id": capability["capability_id"],
        "selected": {
            "frozen_case_index": 0,
            "project": "fixture-project",
            "bug_id": "1",
            "cold": cold,
            "verified": verified,
        },
    }
    write(tmp_path / "DEMO_CASE.json", demo)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    receipt = {
        "protocol": "TRISKELION_DEEPSEEK_HARNESS_CP3_ACCEPTANCE_V1",
        "result": "PASS",
        "capability_id": capability["capability_id"],
        "capability_file_sha256": hashlib.sha256(cap_path.read_bytes()).hexdigest(),
        "handoff_code_commit": commit,
        "harness_commit": "47f943859bef60e4160492346772ded9b24f765a",
        "lifecycle": ["install", "disable", "enable", "uninstall"],
        "demo_case": {"frozen_case_index": 0, "project": "fixture-project", "bug_id": "1"},
    }
    write(tmp_path / "RECEIPT.json", receipt)
    return {
        "capability": cap_path,
        "build": tmp_path / "BUILD_SUMMARY.json",
        "rows": tmp_path / "ROWS.json",
        "results": tmp_path / "RESULTS.json",
        "demo": tmp_path / "DEMO_CASE.json",
        "receipt": tmp_path / "RECEIPT.json",
        "out": tmp_path / "VERIFICATION.json",
    }


def invoke(paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([
        sys.executable,
        "integrations/deepseek-harness/verify_cp3_handoff.py",
        "--capability", str(paths["capability"]),
        "--build-summary", str(paths["build"]),
        "--rows", str(paths["rows"]),
        "--results", str(paths["results"]),
        "--demo", str(paths["demo"]),
        "--receipt", str(paths["receipt"]),
        "--out", str(paths["out"]),
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def test_complete_handoff_chain_passes(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    proc = invoke(paths)
    assert proc.returncode == 0, proc.stdout
    verification = json.loads(paths["out"].read_text())
    assert verification["result"] == "PASS"
    assert verification["demo_case"]["cold_repaired"] is False
    assert verification["demo_case"]["verified_repaired"] is True


def test_tampered_capability_fails_closed(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    capability = json.loads(paths["capability"].read_text())
    capability["rules"][0]["repair_instruction"] = "tampered"
    write(paths["capability"], capability)
    proc = invoke(paths)
    assert proc.returncode != 0
    assert "identity mismatch" in proc.stdout


def test_noncausal_demo_fails_closed(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    demo = json.loads(paths["demo"].read_text())
    demo["selected"]["verified"]["repaired"] = False
    write(paths["demo"], demo)
    proc = invoke(paths)
    assert proc.returncode != 0
    assert "VERIFIED row did not pass" in proc.stdout
