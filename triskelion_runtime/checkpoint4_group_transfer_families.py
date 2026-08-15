from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROTOCOL = "TRISKELION_BUGSINPY_CHECKPOINT4_TRANSFER_FAMILY_V1"
TOKEN_RE = re.compile(r"[a-z][a-z0-9_]+")
CLASS_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)|AssertionError)\b")
COMMIT_RE = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
ABS_PATH_RE = re.compile(r"(?:^|\s)(?:/[^\s:]+|[A-Za-z]:\\[^\s:]+)")
LONG_NUMBER_RE = re.compile(r"\b\d{4,}\b")
STOP = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "into", "not", "none",
    "true", "false", "test", "tests", "pytest", "python", "file", "line", "self",
    "return", "returned", "expected", "actual", "error", "failed", "failure", "assert",
    "assertion", "traceback", "most", "recent", "call", "last", "site", "packages",
})


@dataclass(frozen=True)
class Fingerprint:
    test_tokens: frozenset[str]
    class_tokens: frozenset[str]
    message_tokens: frozenset[str]


def scrub(text: str, project: str, bug_id: str) -> str:
    value = str(text or "")
    value = COMMIT_RE.sub(" ", value)
    value = ABS_PATH_RE.sub(" ", value)
    value = LONG_NUMBER_RE.sub(" ", value)
    if project:
        value = re.sub(re.escape(project), " ", value, flags=re.IGNORECASE)
    if bug_id:
        value = re.sub(rf"\b{re.escape(str(bug_id))}\b", " ", value)
    return value


def tokens(text: str, project: str, bug_id: str, limit: int = 128) -> frozenset[str]:
    cleaned = scrub(text, project, bug_id).casefold()
    found = sorted({t for t in TOKEN_RE.findall(cleaned) if len(t) >= 3 and t not in STOP})
    return frozenset(found[:limit])


def buggy_test_material(row: Mapping[str, Any]) -> tuple[str, str]:
    buggy = row.get("buggy")
    if not isinstance(buggy, Mapping):
        return "", ""
    test = buggy.get("test")
    if not isinstance(test, Mapping):
        return "", ""
    commands: list[str] = []
    outputs: list[str] = []
    for step in test.get("steps", []):
        if not isinstance(step, Mapping):
            continue
        if step.get("command"):
            commands.append(str(step["command"]))
        if step.get("output"):
            outputs.append(str(step["output"]))
    return "\n".join(commands), "\n".join(outputs)


def fingerprint(row: Mapping[str, Any]) -> Fingerprint:
    project = str(row.get("project") or "")
    bug_id = str(row.get("bug_id") or "")
    command, output = buggy_test_material(row)
    scrubbed_output = scrub(output, project, bug_id)
    classes = frozenset(sorted({m.casefold() for m in CLASS_RE.findall(scrubbed_output)})[:128])
    if "assertionerror" in scrubbed_output.casefold():
        classes = frozenset(set(classes) | {"assertionerror"})
    return Fingerprint(
        test_tokens=tokens(command, project, bug_id),
        class_tokens=classes,
        message_tokens=tokens(output, project, bug_id),
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def similarity(a: Fingerprint, b: Fingerprint) -> dict[str, Any]:
    tj = jaccard(a.test_tokens, b.test_tokens)
    mj = jaccard(a.message_tokens, b.message_tokens)
    class_exact = bool(a.class_tokens and b.class_tokens and (a.class_tokens & b.class_tokens))
    score = 0.35 * tj + 0.20 * (1.0 if class_exact else 0.0) + 0.45 * mj
    guard = class_exact or tj >= 0.50
    return {
        "score": round(score, 6),
        "test_jaccard": round(tj, 6),
        "message_jaccard": round(mj, 6),
        "class_exact": class_exact,
        "guard": guard,
        "edge": bool(guard and score >= 0.60),
    }


def global_order(lock: Mapping[str, Any]) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    idx = 0
    for project in lock.get("projects", []):
        name = str(project.get("project") or project.get("name") or "")
        for candidate in project.get("candidate_order", []):
            out[(name, str(candidate.get("bug_id")))] = idx
            idx += 1
    return out


def load_exclusions(causal: Mapping[str, Any]) -> set[tuple[str, str]]:
    excluded: set[tuple[str, str]] = set()
    for key in ("acquisition", "protected"):
        for row in causal.get(key, []):
            if isinstance(row, Mapping):
                excluded.add((str(row.get("project")), str(row.get("bug_id"))))
    return excluded


def case_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("project")), str(row.get("bug_id"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=Path, required=True)
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--checkpoint3-causal", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen grouping evidence")

    attempts = json.loads(args.attempts.read_text())
    lock = json.loads(args.lock.read_text())
    causal = json.loads(args.checkpoint3_causal.read_text())
    if not isinstance(attempts, list) or not isinstance(lock, Mapping) or not isinstance(causal, Mapping):
        raise SystemExit("invalid input")

    order = global_order(lock)
    excluded = load_exclusions(causal)
    qualified = [r for r in attempts if isinstance(r, Mapping) and r.get("classification") == "qualified"]
    fresh = [r for r in qualified if case_key(r) not in excluded]
    missing = [case_key(r) for r in fresh if case_key(r) not in order]
    if missing:
        raise SystemExit(f"qualified case missing from frozen lock: {missing[:3]}")
    fresh.sort(key=lambda r: order[case_key(r)])

    fps = {case_key(r): fingerprint(r) for r in fresh}
    families: list[list[Mapping[str, Any]]] = []
    used: set[tuple[str, str]] = set()

    for seed in fresh:
        sk = case_key(seed)
        if sk in used:
            continue
        family = [seed]
        for candidate in fresh:
            ck = case_key(candidate)
            if ck == sk or ck in used or order[ck] <= order[sk]:
                continue
            if len(family) >= 4:
                break
            if all(similarity(fps[ck], fps[case_key(member)])["edge"] for member in family):
                family.append(candidate)
        if len(family) >= 2:
            families.append(family)
            used.update(case_key(r) for r in family)

    selected = families[0] if families else []
    result: dict[str, Any] = {
        "protocol": PROTOCOL,
        "qualified_fresh_count": len(fresh),
        "family_count": len(families),
        "terminal": "MATCHED_TRANSFER_FAMILY" if selected else "NO_MATCHED_TRANSFER_FAMILY",
        "selected_family": [],
    }
    if selected:
        acquisition = selected[0]
        for i, row in enumerate(selected):
            key = case_key(row)
            pairwise = []
            if i:
                for prior in selected[:i]:
                    pairwise.append({
                        "against": {"project": prior.get("project"), "bug_id": str(prior.get("bug_id"))},
                        **similarity(fps[key], fps[case_key(prior)]),
                    })
            result["selected_family"].append({
                "role": "acquisition" if i == 0 else "protected",
                "project": row.get("project"),
                "bug_id": str(row.get("bug_id")),
                "frozen_order_index": order[key],
                "fingerprint": {
                    "test_tokens": sorted(fps[key].test_tokens),
                    "class_tokens": sorted(fps[key].class_tokens),
                    "message_tokens": sorted(fps[key].message_tokens),
                },
                "pairwise_to_prior": pairwise,
            })

    args.out.mkdir(parents=True)
    (args.out / "CHECKPOINT4_TRANSFER_FAMILY.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not selected:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
