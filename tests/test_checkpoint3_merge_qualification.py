from __future__ import annotations

import copy

import pytest

from triskelion_runtime.checkpoint3_merge_qualification import (
    QUALIFICATION_PROTOCOL,
    UPSTREAM_COMMIT,
    merge_qualification_evidence,
)


def lock_fixture() -> dict:
    return {
        "commit": UPSTREAM_COMMIT,
        "projects": [
            {"project": "pandas", "split": "acquisition"},
            {"project": "ansible", "split": "protected"},
            {"project": "tqdm", "split": "protected"},
        ],
    }


def selected(project: str, bug_id: str, rank: str, split: str) -> dict:
    return {"project": project, "bug_id": bug_id, "rank": rank, "split": split}


def summary(rows: list[dict], revision: str) -> dict:
    return {
        "protocol": QUALIFICATION_PROTOCOL,
        "upstream_commit": UPSTREAM_COMMIT,
        "harness_revision": revision,
        "selected": rows,
    }


def attempt(
    project: str,
    bug_id: str,
    rank: str,
    classification: str = "qualified",
    python_version: str = "3.8",
) -> dict:
    return {
        "project": project,
        "bug_id": bug_id,
        "rank": rank,
        "classification": classification,
        "python_version_declared": python_version,
    }


def test_merge_restores_original_frozen_project_order_and_hex_rank_order_across_runs() -> None:
    sources = [
        (
            summary(
                [
                    selected("pandas", "5", "a100", "acquisition"),
                    selected("tqdm", "2", "f000", "protected"),
                ],
                "V2_3",
            ),
            [
                attempt("tqdm", "2", "f000", python_version="3.6"),
                attempt("pandas", "6", "0f00", classification="infrastructure_negative"),
                attempt("pandas", "5", "a100"),
            ],
        ),
        (
            summary([selected("ansible", "7", "00ff", "protected")], "V2_2"),
            [attempt("ansible", "7", "00ff", python_version="3.6")],
        ),
    ]

    merged, attempts = merge_qualification_evidence(sources, lock=lock_fixture())

    assert merged["projects_with_evidence"] == 3
    assert merged["projects_missing_evidence"] == []
    assert [row["project"] for row in merged["selected"]] == ["pandas", "ansible", "tqdm"]
    assert [row["python_version_declared"] for row in merged["selected"]] == ["3.8", "3.6", "3.6"]
    assert [(row["project"], row["rank"]) for row in attempts] == [
        ("pandas", "0f00"),
        ("pandas", "a100"),
        ("ansible", "00ff"),
        ("tqdm", "f000"),
    ]
    assert merged["harness_revisions"] == ["V2_2", "V2_3"]


def test_merge_reports_missing_evidence_without_silently_dropping_project() -> None:
    sources = [
        (
            summary([selected("pandas", "5", "abc0", "acquisition")], "V2_3"),
            [attempt("pandas", "5", "abc0")],
        )
    ]
    merged, _ = merge_qualification_evidence(sources, lock=lock_fixture())
    assert merged["projects_missing_evidence"] == ["ansible", "tqdm"]


def test_merge_rejects_conflicting_selected_evidence_for_same_project() -> None:
    first = summary([selected("ansible", "7", "a100", "protected")], "V2_1")
    second = copy.deepcopy(first)
    second["selected"][0]["bug_id"] = "8"
    second["selected"][0]["rank"] = "b100"

    with pytest.raises(ValueError, match="conflicting selected evidence"):
        merge_qualification_evidence(
            [
                (first, [attempt("ansible", "7", "a100")]),
                (second, [attempt("ansible", "8", "b100")]),
            ],
            lock=lock_fixture(),
        )


def test_merge_rejects_project_outside_frozen_lock() -> None:
    bad = summary([selected("unknown", "1", "c100", "protected")], "V2")
    with pytest.raises(ValueError, match="outside frozen lock"):
        merge_qualification_evidence(
            [(bad, [attempt("unknown", "1", "c100")])], lock=lock_fixture()
        )


def test_merge_rejects_selected_case_without_declared_python_runtime() -> None:
    selected_summary = summary([selected("pandas", "5", "deadbeef", "acquisition")], "V2")
    bad_attempt = attempt("pandas", "5", "deadbeef")
    bad_attempt.pop("python_version_declared")
    with pytest.raises(ValueError, match="missing python_version_declared"):
        merge_qualification_evidence([(selected_summary, [bad_attempt])], lock=lock_fixture())
