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


def summary(selected: list[dict], revision: str) -> dict:
    return {
        "protocol": QUALIFICATION_PROTOCOL,
        "upstream_commit": UPSTREAM_COMMIT,
        "harness_revision": revision,
        "selected": selected,
    }


def attempt(
    project: str,
    rank: int,
    classification: str = "qualified",
    python_version: str = "3.8",
) -> dict:
    return {
        "project": project,
        "bug_id": str(rank),
        "rank": rank,
        "classification": classification,
        "python_version_declared": python_version,
    }


def test_merge_restores_original_frozen_project_order_across_runs() -> None:
    sources = [
        (
            summary(
                [
                    {"project": "pandas", "bug_id": "5", "split": "acquisition"},
                    {"project": "tqdm", "bug_id": "2", "split": "protected"},
                ],
                "V2_3",
            ),
            [attempt("tqdm", 2, python_version="3.6"), attempt("pandas", 5)],
        ),
        (
            summary(
                [{"project": "ansible", "bug_id": "7", "split": "protected"}],
                "V2_2",
            ),
            [attempt("ansible", 7, python_version="3.6")],
        ),
    ]

    merged, attempts = merge_qualification_evidence(sources, lock=lock_fixture())

    assert merged["projects_with_evidence"] == 3
    assert merged["projects_missing_evidence"] == []
    assert [row["project"] for row in merged["selected"]] == ["pandas", "ansible", "tqdm"]
    assert [row["python_version_declared"] for row in merged["selected"]] == ["3.8", "3.6", "3.6"]
    assert [row["project"] for row in attempts] == ["pandas", "ansible", "tqdm"]
    assert merged["harness_revisions"] == ["V2_2", "V2_3"]


def test_merge_reports_missing_evidence_without_silently_dropping_project() -> None:
    sources = [
        (
            summary([{"project": "pandas", "bug_id": "5", "split": "acquisition"}], "V2_3"),
            [attempt("pandas", 5)],
        )
    ]
    merged, _ = merge_qualification_evidence(sources, lock=lock_fixture())
    assert merged["projects_missing_evidence"] == ["ansible", "tqdm"]


def test_merge_rejects_conflicting_selected_evidence_for_same_project() -> None:
    first = summary([{"project": "ansible", "bug_id": "7", "split": "protected"}], "V2_1")
    second = copy.deepcopy(first)
    second["selected"][0]["bug_id"] = "8"

    with pytest.raises(ValueError, match="conflicting selected evidence"):
        merge_qualification_evidence(
            [(first, [attempt("ansible", 7)]), (second, [attempt("ansible", 8)])],
            lock=lock_fixture(),
        )


def test_merge_rejects_project_outside_frozen_lock() -> None:
    bad = summary([{"project": "unknown", "bug_id": "1", "split": "protected"}], "V2")
    with pytest.raises(ValueError, match="outside frozen lock"):
        merge_qualification_evidence([(bad, [attempt("unknown", 1)])], lock=lock_fixture())


def test_merge_rejects_selected_case_without_declared_python_runtime() -> None:
    selected = summary([{"project": "pandas", "bug_id": "5", "split": "acquisition"}], "V2")
    bad_attempt = attempt("pandas", 5)
    bad_attempt.pop("python_version_declared")
    with pytest.raises(ValueError, match="missing python_version_declared"):
        merge_qualification_evidence([(selected, [bad_attempt])], lock=lock_fixture())
