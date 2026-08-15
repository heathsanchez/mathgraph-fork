from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from triskelion_runtime.checkpoint3_capability import RepairRule, public_capability_payload


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "integrations" / "deepseek-harness" / "bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("triskelion_deepseek_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_route_ablate_restore_uninstall(tmp_path, monkeypatch) -> None:
    bridge = load_bridge()
    state = tmp_path / ".triskelion" / "deepseek-harness"
    monkeypatch.setattr(bridge, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "STATE_ROOT", state)
    monkeypatch.setattr(bridge, "REGISTRY_PATH", state / "registry.json")
    monkeypatch.setattr(bridge, "CAPABILITY_DIR", state / "capabilities")

    rule = RepairRule(
        rule_id="rule-keyerror",
        title="Guard missing mapping key",
        required_any=("keyerror",),
        required_all=(),
        forbidden_any=("indexerror",),
        repair_instruction="Handle a missing mapping key without changing unrelated branches.",
        evidence_project="acquisition-only",
        evidence_bug_id="1",
    )
    payload = public_capability_payload(
        (rule,), build_protocol_sha256="0" * 64, compile_failures=()
    )
    source = tmp_path / "CAPABILITY.json"
    source.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    installed = bridge.dispatch({"action": "install", "capability_path": "CAPABILITY.json"})
    capability_id = installed["capability_id"]
    assert installed["enabled"] is True

    routed = bridge.dispatch({"action": "route", "visible_context": "Failure: KeyError in mapping lookup"})
    assert routed["activated"] is True
    assert routed["matched_rule_ids"] == ["rule-keyerror"]
    assert "missing mapping key" in routed["guidance"]

    disabled = bridge.dispatch({"action": "disable", "capability_id": capability_id})
    assert disabled["enabled"] is False
    ablated = bridge.dispatch({"action": "route", "visible_context": "Failure: KeyError in mapping lookup"})
    assert ablated["activated"] is False
    assert ablated["guidance"] == ""

    bridge.dispatch({"action": "enable", "capability_id": capability_id})
    restored = bridge.dispatch({"action": "route", "visible_context": "Failure: KeyError in mapping lookup"})
    assert restored["activated"] is True

    bridge.dispatch({"action": "uninstall", "capability_id": capability_id})
    assert bridge.dispatch({"action": "status"})["capabilities"] == []


def test_install_rejects_tampered_content_address(tmp_path, monkeypatch) -> None:
    bridge = load_bridge()
    state = tmp_path / ".triskelion" / "deepseek-harness"
    monkeypatch.setattr(bridge, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "STATE_ROOT", state)
    monkeypatch.setattr(bridge, "REGISTRY_PATH", state / "registry.json")
    monkeypatch.setattr(bridge, "CAPABILITY_DIR", state / "capabilities")

    payload = {
        "capability_id": "0" * 64,
        "build_protocol": "test",
        "build_protocol_sha256": "0" * 64,
        "rules": [],
        "compile_failures": [],
    }
    source = tmp_path / "CAPABILITY.json"
    source.write_text(json.dumps(payload))

    try:
        bridge.dispatch({"action": "install", "capability_path": "CAPABILITY.json"})
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("tampered capability should be rejected")
