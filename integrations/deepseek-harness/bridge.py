from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(os.environ.get("TRISKELION_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from triskelion_runtime.checkpoint3_eval_core import arm_context, rule_from_public

STATE_ROOT = REPO_ROOT / ".triskelion" / "deepseek-harness"
REGISTRY_PATH = STATE_ROOT / "registry.json"
CAPABILITY_DIR = STATE_ROOT / "capabilities"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"version": 1, "capabilities": {}}
    value = json.loads(REGISTRY_PATH.read_text())
    if not isinstance(value, Mapping) or value.get("version") != 1:
        raise ValueError("invalid Triskelion DeepSeek Harness registry")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, Mapping):
        raise ValueError("registry capabilities must be an object")
    return {"version": 1, "capabilities": dict(capabilities)}


def _save_registry(registry: Mapping[str, Any]) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    CAPABILITY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")
    tmp.replace(REGISTRY_PATH)


def _safe_repo_file(raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("capability_path must be a non-empty string")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("capability_path must stay inside the Triskelion repository") from exc
    if not candidate.is_file():
        raise ValueError(f"capability file not found: {candidate}")
    return candidate


def _validate_capability(payload: Any) -> tuple[str, list[Any]]:
    if not isinstance(payload, Mapping):
        raise ValueError("capability root must be an object")
    capability_id = payload.get("capability_id")
    rules_raw = payload.get("rules")
    if not isinstance(capability_id, str) or len(capability_id) != 64:
        raise ValueError("capability_id must be a sha256 hex string")
    try:
        int(capability_id, 16)
    except ValueError as exc:
        raise ValueError("capability_id must be hexadecimal") from exc
    if not isinstance(rules_raw, list):
        raise ValueError("capability rules must be an array")
    rules = [rule_from_public(rule) for rule in rules_raw]
    unsigned = dict(payload)
    unsigned.pop("capability_id", None)
    expected = _sha256_bytes(_canonical_json(unsigned))
    if expected != capability_id:
        raise ValueError("capability_id does not match canonical capability payload")
    return capability_id, rules


def _load_installed_payload(capability_id: str) -> Mapping[str, Any]:
    path = CAPABILITY_DIR / f"{capability_id}.json"
    if not path.is_file():
        raise ValueError(f"installed capability payload missing: {capability_id}")
    payload = json.loads(path.read_text())
    checked_id, _ = _validate_capability(payload)
    if checked_id != capability_id:
        raise ValueError("installed capability identity mismatch")
    return payload


def _status() -> dict[str, Any]:
    registry = _load_registry()
    rows = []
    for capability_id, record in sorted(registry["capabilities"].items()):
        payload = _load_installed_payload(capability_id)
        rows.append(
            {
                "capability_id": capability_id,
                "enabled": bool(record.get("enabled")),
                "rule_count": len(payload.get("rules", [])),
                "source": record.get("source"),
                "source_sha256": record.get("source_sha256"),
            }
        )
    return {
        "ok": True,
        "runtime": "triskelion-deepseek-harness-v1",
        "registry": str(REGISTRY_PATH.relative_to(REPO_ROOT)),
        "capabilities": rows,
    }


def _install(request: Mapping[str, Any]) -> dict[str, Any]:
    source = _safe_repo_file(str(request.get("capability_path", "")))
    source_bytes = source.read_bytes()
    payload = json.loads(source_bytes)
    capability_id, rules = _validate_capability(payload)
    registry = _load_registry()
    CAPABILITY_DIR.mkdir(parents=True, exist_ok=True)
    target = CAPABILITY_DIR / f"{capability_id}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    registry["capabilities"][capability_id] = {
        "enabled": True,
        "source": str(source.relative_to(REPO_ROOT)),
        "source_sha256": _sha256_bytes(source_bytes),
    }
    _save_registry(registry)
    return {
        "ok": True,
        "action": "install",
        "capability_id": capability_id,
        "enabled": True,
        "rule_count": len(rules),
    }


def _set_enabled(request: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
    capability_id = str(request.get("capability_id", ""))
    registry = _load_registry()
    record = registry["capabilities"].get(capability_id)
    if not isinstance(record, Mapping):
        raise ValueError(f"capability not installed: {capability_id}")
    registry["capabilities"][capability_id] = {**record, "enabled": enabled}
    _save_registry(registry)
    return {
        "ok": True,
        "action": "enable" if enabled else "disable",
        "capability_id": capability_id,
        "enabled": enabled,
    }


def _uninstall(request: Mapping[str, Any]) -> dict[str, Any]:
    capability_id = str(request.get("capability_id", ""))
    registry = _load_registry()
    if capability_id not in registry["capabilities"]:
        raise ValueError(f"capability not installed: {capability_id}")
    registry["capabilities"].pop(capability_id)
    payload = CAPABILITY_DIR / f"{capability_id}.json"
    if payload.exists():
        payload.unlink()
    _save_registry(registry)
    return {"ok": True, "action": "uninstall", "capability_id": capability_id}


def _route(request: Mapping[str, Any]) -> dict[str, Any]:
    visible_context = request.get("visible_context")
    if not isinstance(visible_context, str):
        raise ValueError("visible_context must be a string")
    registry = _load_registry()
    all_rules = []
    enabled_ids = []
    for capability_id, record in sorted(registry["capabilities"].items()):
        if not bool(record.get("enabled")):
            continue
        payload = _load_installed_payload(capability_id)
        _, rules = _validate_capability(payload)
        all_rules.extend(rules)
        enabled_ids.append(capability_id)
    routed = arm_context(
        "verified",
        visible_context=visible_context,
        rules=tuple(all_rules),
        raw_memory_text="",
    )
    return {
        "ok": True,
        "action": "route",
        "activated": routed.activated,
        "enabled_capability_ids": enabled_ids,
        "matched_rule_ids": list(routed.matched_rule_ids),
        "guidance": routed.text,
        "false_activation": routed.false_activation,
    }


def dispatch(request: Mapping[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if action == "status":
        return _status()
    if action == "install":
        return _install(request)
    if action == "enable":
        return _set_enabled(request, True)
    if action == "disable":
        return _set_enabled(request, False)
    if action == "uninstall":
        return _uninstall(request)
    if action == "route":
        return _route(request)
    raise ValueError(f"unknown action: {action}")


def main() -> None:
    try:
        request = json.loads(sys.stdin.read())
        if not isinstance(request, Mapping):
            raise ValueError("request must be a JSON object")
        response = dispatch(request)
    except Exception as exc:
        response = {
            "ok": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }
    sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
