from __future__ import annotations

import copy

import pytest

from triskelion_runtime.checkpoint3_causal_protocol import default_protocol_path
from triskelion_runtime.checkpoint3_freeze_causal_corpus import freeze_causal_corpus


def qualification_fixture() -> dict:
    return {
        "protocol": "TRISKELION_BUGSINPY_CHECKPOINT3_QUALIFICATION_V1",
        "upstream_commit": "11c5f1eea954a42132cfd06bf257766a7963e0fd",
        "harness_revisions": ["V2_3"],
        "selected": [
            {
                "project": "httpie",
                "bug_id": "5",
                "split": "acquisition",
                "buggy_commit": "buggy-a",
                "fixed_commit": "fixed-a",
                "test_file": "test_a.py",
            },
            {
                "project": "black",
                "bug_id": "18",
                "split": "protected",
                "buggy_commit": "buggy-b",
                "fixed_commit": "fixed-b",
                "test_file": "test_b.py",
            },
        ],
    }


def test_freeze_uses_every_qualified_case_without_manual_selection() -> None:
    frozen = freeze_causal_corpus(
        qualification_fixture(), protocol_path=default_protocol_path()
    )

    assert frozen["qualified_project_count"] == 2
    assert frozen["acquisition_count"] == 1
    assert frozen["protected_count"] == 1
    assert [x["project"] for x in frozen["acquisition"]] == ["httpie"]
    assert [x["project"] for x in frozen["protected"]] == ["black"]
    assert "no manual case selection" in frozen["selection_rule"]
    assert len(frozen["causal_protocol_sha256"]) == 64


def test_freeze_rejects_duplicate_projects() -> None:
    qualification = qualification_fixture()
    qualification["selected"].append(copy.deepcopy(qualification["selected"][0]))

    with pytest.raises(ValueError, match="duplicate selected project"):
        freeze_causal_corpus(qualification, protocol_path=default_protocol_path())


def test_freeze_rejects_split_drift() -> None:
    qualification = qualification_fixture()
    qualification["selected"][0]["split"] = "tuning"

    with pytest.raises(ValueError, match="unexpected split"):
        freeze_causal_corpus(qualification, protocol_path=default_protocol_path())


def test_freeze_rejects_wrong_upstream_commit() -> None:
    qualification = qualification_fixture()
    qualification["upstream_commit"] = "wrong"

    with pytest.raises(ValueError, match="upstream commit mismatch"):
        freeze_causal_corpus(qualification, protocol_path=default_protocol_path())
