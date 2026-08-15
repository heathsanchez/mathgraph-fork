from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from triskelion_runtime.checkpoint3_causal_protocol import (
    QUALIFICATION_PROTOCOL_ID,
    load_protocol,
)

FREEZE_ID = "TRISKELION_BUGSINPY_CHECKPOINT3_CAUSAL_CORPUS_V1"
PROTECTED_FORBIDDEN_FIELDS = frozenset({
    "fixed_commit",
    "fixed_source",
    "fixed_tree",
    "patch",
    "gold_patch",
    "reference_patch",
    "solution",
})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitize_protected_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = {key: value for key, value in raw.items() if key not in PROTECTED_FORBIDDEN_FIELDS}
    leaked = sorted(PROTECTED_FORBIDDEN_FIELDS.intersection(item))
    if leaked:
        raise ValueError(f"protected item retained forbidden fields: {leaked}")
    return item


def freeze_causal_corpus(
    qualification: Mapping[str, Any],
    *,
    protocol_path: Path,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    if qualification.get("protocol") != QUALIFICATION_PROTOCOL_ID:
        raise ValueError("qualification protocol mismatch")
    if qualification.get("upstream_commit") != protocol.upstream_commit:
        raise ValueError("qualification upstream commit mismatch")

    selected = qualification.get("selected")
    if not isinstance(selected, list):
        raise ValueError("qualification selected must be an array")

    seen_projects: set[str] = set()
    acquisition: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    for raw in selected:
        if not isinstance(raw, Mapping):
            raise ValueError("selected entries must be objects")
        project = raw.get("project")
        bug_id = raw.get("bug_id")
        split = raw.get("split")
        if not isinstance(project, str) or not project:
            raise ValueError("selected project must be non-empty")
        if not isinstance(bug_id, str) or not bug_id:
            raise ValueError("selected bug_id must be non-empty")
        if project in seen_projects:
            raise ValueError(f"duplicate selected project: {project}")
        seen_projects.add(project)
        if split not in ("acquisition", "protected"):
            raise ValueError(f"unexpected split for {project}: {split}")

        if split == "acquisition":
            acquisition.append(dict(raw))
        else:
            protected.append(_sanitize_protected_item(raw))

    # Preserve the qualification aggregate's deterministic selected ordering.
    return {
        "freeze_protocol": FREEZE_ID,
        "causal_protocol": protocol.protocol,
        "causal_protocol_sha256": _sha256(protocol_path),
        "qualification_protocol": qualification["protocol"],
        "qualification_upstream_commit": qualification["upstream_commit"],
        "qualification_harness_revisions": qualification.get("harness_revisions", []),
        "qualified_project_count": len(selected),
        "acquisition_count": len(acquisition),
        "protected_count": len(protected),
        "acquisition": acquisition,
        "protected": protected,
        "selection_rule": "all qualified projects from the immutable qualification aggregate; no manual case selection",
        "protected_source_access_before_freeze": "forbidden",
        "protected_forbidden_fields_stripped": sorted(PROTECTED_FORBIDDEN_FIELDS),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qualification", type=Path, required=True)
    ap.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).with_name("CHECKPOINT3_CAUSAL_PROTOCOL_V1.json"),
    )
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen causal corpus")
    qualification = json.loads(args.qualification.read_text())
    if not isinstance(qualification, Mapping):
        raise SystemExit("qualification root must be an object")
    frozen = freeze_causal_corpus(qualification, protocol_path=args.protocol)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    print(json.dumps(frozen, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
