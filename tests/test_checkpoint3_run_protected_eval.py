from __future__ import annotations

import hashlib
import json

import pytest

from triskelion_runtime.checkpoint3_run_protected_eval import (
    baseline_failure_text,
    docker_image_for,
    protected_test_text,
    raw_memory_context,
    selected_source_text,
)


def test_python_runtime_routes_to_frozen_target_image() -> None:
    images = {"3.6": "py36", "3.7": "py37", "3.8": "py38"}
    assert docker_image_for("3.6", images) == "py36"
    assert docker_image_for("3.8.20", images) == "py38"
    with pytest.raises(ValueError, match="unsupported frozen Python"):
        docker_image_for("3.9", images)


def test_baseline_failure_text_uses_only_compact_test_evidence() -> None:
    prepared = {
        "baseline": {
            "steps": [
                {"command": "pytest -q", "output": "FAILED regression", "returncode": 1},
            ]
        }
    }
    text = baseline_failure_text(prepared)
    assert "$ pytest -q" in text
    assert "FAILED regression" in text
    assert "[returncode=1]" in text


def test_protected_test_text_hash_checks_bundle(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    payload = b"def test_x():\n    assert True\n"
    source = bundle / "files/case-00/tests/test_x.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    manifest = {
        "records": [{
            "case_index": 0,
            "files": [{
                "relative_path": "tests/test_x.py",
                "bundle_path": "files/case-00/tests/test_x.py",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }],
        }]
    }
    (bundle / "MANIFEST.json").write_text(json.dumps(manifest))
    text, paths = protected_test_text(bundle, 0)
    assert paths == ("tests/test_x.py",)
    assert "assert True" in text
    source.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        protected_test_text(bundle, 0)


def test_selected_source_text_rejects_test_or_missing_file(tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg/core.py").write_text("value = 1\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_core.py").write_text("assert True\n")
    text = selected_source_text(
        repo,
        ("pkg/core.py",),
        test_paths=("tests/test_core.py",),
        limit=1000,
    )
    assert "value = 1" in text
    with pytest.raises(ValueError, match="protected test"):
        selected_source_text(repo, ("tests/test_core.py",), test_paths=("tests/test_core.py",), limit=1000)
    with pytest.raises(ValueError, match="does not exist"):
        selected_source_text(repo, ("pkg/missing.py",), test_paths=(), limit=1000)


def test_raw_memory_context_is_deterministic_and_bounded() -> None:
    memory = [{"case_index": 0, "gold_diff": "x" * 1000}]
    first = raw_memory_context(memory, 200)
    second = raw_memory_context(memory, 200)
    assert first == second
    assert len(first) == 200
