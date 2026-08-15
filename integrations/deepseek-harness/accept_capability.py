from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


def load_bridge(repo_root: Path) -> ModuleType:
    path = repo_root / "integrations" / "deepseek-harness" / "bridge.py"
    spec = importlib.util.spec_from_file_location("triskelion_deepseek_harness_bridge", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load DeepSeek Harness bridge")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Acceptance-test a real Triskelion CAPABILITY.json through the DeepSeek Harness bridge lifecycle."
    )
    ap.add_argument("capability", type=Path)
    ap.add_argument(
        "--visible-context",
        default="",
        help="Optional context used only to exercise deterministic routing; no activation is required.",
    )
    args = ap.parse_args()

    repo_root = Path(os.environ.get("TRISKELION_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
    os.environ["TRISKELION_REPO_ROOT"] = str(repo_root)
    capability = args.capability.resolve()
    try:
        relative = capability.relative_to(repo_root)
    except ValueError as exc:
        raise SystemExit("capability must be inside the repository checkout") from exc

    payload = json.loads(capability.read_text())
    require(isinstance(payload, Mapping), "capability root must be an object")
    expected_id = payload.get("capability_id")
    require(isinstance(expected_id, str) and len(expected_id) == 64, "missing capability_id")

    bridge = load_bridge(repo_root)

    installed = bridge.dispatch({"action": "install", "capability_path": str(relative)})
    require(installed.get("ok") is True, "install failed")
    require(installed.get("capability_id") == expected_id, "installed content identity drifted")
    require(installed.get("enabled") is True, "installed capability was not enabled")

    status = bridge.dispatch({"action": "status"})
    rows = status.get("capabilities", [])
    require(
        any(row.get("capability_id") == expected_id and row.get("enabled") is True for row in rows),
        "enabled capability missing from registry status",
    )

    routed_before: Mapping[str, Any] | None = None
    routed_disabled: Mapping[str, Any] | None = None
    routed_restored: Mapping[str, Any] | None = None
    if args.visible_context:
        routed_before = bridge.dispatch({"action": "route", "visible_context": args.visible_context})
        require(expected_id in routed_before.get("enabled_capability_ids", []), "enabled capability missing from route")

    disabled = bridge.dispatch({"action": "disable", "capability_id": expected_id})
    require(disabled.get("enabled") is False, "disable failed")
    if args.visible_context:
        routed_disabled = bridge.dispatch({"action": "route", "visible_context": args.visible_context})
        require(expected_id not in routed_disabled.get("enabled_capability_ids", []), "disabled capability still routed")

    enabled = bridge.dispatch({"action": "enable", "capability_id": expected_id})
    require(enabled.get("enabled") is True, "enable failed")
    if args.visible_context:
        routed_restored = bridge.dispatch({"action": "route", "visible_context": args.visible_context})
        require(expected_id in routed_restored.get("enabled_capability_ids", []), "restored capability missing from route")
        require(
            routed_before.get("matched_rule_ids") == routed_restored.get("matched_rule_ids")
            and routed_before.get("guidance") == routed_restored.get("guidance"),
            "disable/enable cycle changed deterministic routing",
        )

    bridge.dispatch({"action": "uninstall", "capability_id": expected_id})
    final_status = bridge.dispatch({"action": "status"})
    require(
        all(row.get("capability_id") != expected_id for row in final_status.get("capabilities", [])),
        "uninstalled capability remains in registry",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "capability_id": expected_id,
                "rule_count": installed.get("rule_count"),
                "lifecycle": ["install", "disable", "enable", "uninstall"],
                "routing_exercised": bool(args.visible_context),
                "activated_before_disable": (
                    routed_before.get("activated") if routed_before is not None else None
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
