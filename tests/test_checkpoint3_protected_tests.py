from __future__ import annotations

import hashlib

import pytest

import triskelion_runtime.checkpoint3_protected_tests as protected_tests


def test_safe_test_paths_accepts_multiple_relative_paths() -> None:
    assert protected_tests.safe_test_paths("tests/test_a.py;tests/test_b.py") == (
        "tests/test_a.py",
        "tests/test_b.py",
    )


@pytest.mark.parametrize(
    "value",
    ["../secret.py", "/tmp/test.py", "C:\\tmp\\test.py", "tests/../../secret.py"],
)
def test_safe_test_paths_rejects_traversal_and_absolute_paths(value: str) -> None:
    with pytest.raises(ValueError, match="unsafe protected test path"):
        protected_tests.safe_test_paths(value)


def test_bundle_materializes_only_declared_test_blobs(monkeypatch, tmp_path) -> None:
    selected = [
        {
            "project": "protected-project",
            "bug_id": "7",
            "split": "protected",
            "repository": "https://example.invalid/repo.git",
            "fixed_commit": "fixed-secret",
            "test_file": "tests/test_regression.py",
            "python_version_declared": "3.8",
        },
        {
            "project": "acquisition-project",
            "bug_id": "2",
            "split": "acquisition",
            "repository": "https://example.invalid/other.git",
            "fixed_commit": "allowed-acquisition",
            "test_file": "tests/test_other.py",
            "python_version_declared": "3.8",
        },
    ]
    payload = b"def test_regression():\n    assert True\n"
    calls = []

    def fake_show(repository, fixed_commit, paths, timeout=180):
        calls.append((repository, fixed_commit, tuple(paths)))
        return {"tests/test_regression.py": payload}

    monkeypatch.setattr(protected_tests, "_git_show_files", fake_show)
    out = tmp_path / "bundle"
    manifest = protected_tests.build_protected_test_bundle(selected, out_dir=out)

    assert calls == [
        (
            "https://example.invalid/repo.git",
            "fixed-secret",
            ("tests/test_regression.py",),
        )
    ]
    assert manifest["protected_case_count"] == 1
    assert manifest["fixed_production_source_materialized"] is False
    assert manifest["gold_patch_materialized"] is False
    record = manifest["records"][0]
    assert "fixed_commit" not in record
    file_row = record["files"][0]
    assert file_row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (out / file_row["bundle_path"]).read_bytes() == payload
