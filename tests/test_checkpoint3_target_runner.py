from __future__ import annotations

import hashlib
import json

import triskelion_runtime.checkpoint3_target_runner as target


def write_bundle(tmp_path, payload=b"def test_x():\n    assert True\n"):
    bundle = tmp_path / "bundle"
    source = bundle / "files" / "case-00" / "tests" / "test_x.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    manifest = {
        "records": [
            {
                "case_index": 0,
                "files": [
                    {
                        "relative_path": "tests/test_x.py",
                        "bundle_path": "files/case-00/tests/test_x.py",
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        ]
    }
    (bundle / "MANIFEST.json").write_text(json.dumps(manifest))
    return bundle, payload


def test_restore_pristine_resets_then_restores_hash_checked_test(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle, payload = write_bundle(tmp_path)
    calls = []

    def fake_git(repo_arg, args, timeout=180):
        calls.append(tuple(args))
        return {"returncode": 0, "output": "ok"}

    monkeypatch.setattr(target, "run_git", fake_git)
    result = target.restore_pristine(repo, "deadbeef", bundle, 0)
    assert result["ok"] is True
    assert calls == [("reset", "--hard", "deadbeef")]
    assert (repo / "tests/test_x.py").read_bytes() == payload


def test_restore_pristine_rejects_tampered_test_bundle(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle, _ = write_bundle(tmp_path)
    (bundle / "files/case-00/tests/test_x.py").write_bytes(b"tampered")
    monkeypatch.setattr(target, "run_git", lambda *args, **kwargs: {"returncode": 0, "output": "ok"})
    result = target.restore_pristine(repo, "deadbeef", bundle, 0)
    assert result["ok"] is False
    assert result["stage"] == "test_bundle_hash"


def test_prepare_requires_baseline_regression_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(target, "restore_pristine", lambda *args, **kwargs: {"ok": True, "stage": "complete"})
    monkeypatch.setattr(target, "provision", lambda *args, **kwargs: {"ok": True, "stage": "complete"})
    monkeypatch.setattr(target, "relevant_tests", lambda *args, **kwargs: {"ok": True, "test_passed": True})
    result = target.prepare(tmp_path, "buggy", tmp_path, tmp_path, 0, 10)
    assert result["ok"] is False
    assert result["stage"] == "baseline_unreproduced"


def test_evaluate_patch_nonapplication_is_competence_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(target, "restore_pristine", lambda *args, **kwargs: {"ok": True, "stage": "complete"})
    monkeypatch.setattr(target, "apply_patch", lambda *args, **kwargs: {"ok": False, "stage": "patch_check"})
    result = target.evaluate(tmp_path, "buggy", tmp_path, tmp_path, 0, tmp_path / "patch.diff", 10)
    assert result["ok"] is True
    assert result["classification"] == "competence"
    assert result["patch_applied"] is False
    assert result["repaired"] is False


def test_evaluate_executed_regression_sets_repair_verdict(monkeypatch, tmp_path):
    monkeypatch.setattr(target, "restore_pristine", lambda *args, **kwargs: {"ok": True, "stage": "complete"})
    monkeypatch.setattr(target, "apply_patch", lambda *args, **kwargs: {"ok": True, "stage": "patch_apply"})
    monkeypatch.setattr(target, "relevant_tests", lambda *args, **kwargs: {"ok": True, "test_passed": True})
    result = target.evaluate(tmp_path, "buggy", tmp_path, tmp_path, 0, tmp_path / "patch.diff", 10)
    assert result["classification"] == "competence"
    assert result["patch_applied"] is True
    assert result["test_executed"] is True
    assert result["repaired"] is True
