from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

BUNDLE_PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT3_PROTECTED_TEST_BUNDLE_V1"


def safe_test_paths(test_file: str) -> tuple[str, ...]:
    paths: list[str] = []
    for raw in test_file.split(";"):
        raw = raw.strip().replace("\\", "/")
        if not raw:
            continue
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or not path.parts or ":" in raw:
            raise ValueError(f"unsafe protected test path: {raw}")
        normalized = str(path)
        if normalized not in paths:
            paths.append(normalized)
    if not paths:
        raise ValueError("protected case has no test paths")
    return tuple(paths)


def _git_show_files(
    repository: str,
    fixed_commit: str,
    paths: Sequence[str],
    *,
    timeout: int = 180,
) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="triskelion_cp3_tests_") as td:
        repo = Path(td) / "repo"
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True, timeout=timeout)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", repository],
            check=True,
            timeout=timeout,
        )
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "--quiet", "--depth=1", "origin", fixed_commit],
            check=True,
            timeout=timeout,
        )
        out: dict[str, bytes] = {}
        for path in paths:
            proc = subprocess.run(
                ["git", "-C", str(repo), "show", f"{fixed_commit}:{path}"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            out[path] = proc.stdout
        return out


def build_protected_test_bundle(
    selected: Sequence[Mapping[str, Any]],
    *,
    out_dir: Path,
) -> dict[str, Any]:
    protected = [row for row in selected if row.get("split") == "protected"]
    out_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    for case_index, case in enumerate(protected):
        required = (
            "project",
            "bug_id",
            "repository",
            "fixed_commit",
            "test_file",
            "python_version_declared",
        )
        if any(not case.get(field) for field in required):
            raise ValueError(f"protected case missing test-bundle field at index {case_index}")
        paths = safe_test_paths(str(case["test_file"]))
        blobs = _git_show_files(str(case["repository"]), str(case["fixed_commit"]), paths)
        files: list[dict[str, Any]] = []
        for relative in paths:
            payload = blobs[relative]
            destination = out_dir / "files" / f"case-{case_index:02d}" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            files.append(
                {
                    "relative_path": relative,
                    "bundle_path": str(destination.relative_to(out_dir)).replace("\\", "/"),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
            )
        records.append(
            {
                "case_index": case_index,
                "project": str(case["project"]),
                "bug_id": str(case["bug_id"]),
                "python_version_declared": str(case["python_version_declared"]),
                "files": files,
            }
        )
    manifest = {
        "protocol": BUNDLE_PROTOCOL,
        "protected_case_count": len(records),
        "fixed_production_source_materialized": False,
        "gold_patch_materialized": False,
        "records": records,
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qualification", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite protected test bundle")
    qualification = json.loads(args.qualification.read_text())
    selected = qualification.get("selected") if isinstance(qualification, Mapping) else None
    if not isinstance(selected, list):
        raise SystemExit("qualification selected must be an array")
    manifest = build_protected_test_bundle(selected, out_dir=args.out)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
