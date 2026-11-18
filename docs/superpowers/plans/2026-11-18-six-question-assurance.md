# Six-question Assurance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task; steps use checkbox syntax.

**Goal:** Implement and test the smallest executable six-question, source-conditional assurance gate in the existing finite research module.

**Architecture:** Wrap `structural.assess` without changing the frozen dataset. Accept typed obligations, exact provenance bytes, a trusted caller-supplied replay, and requirement/permission context. Keep six distinct check outputs plus a conservative final verdict.

**Tech Stack:** Python 3.10+, standard library, pytest; optional Node.js for Open MCT source-derived integration.

**Spec:** `docs/superpowers/specs/2026-11-18-six-question-assurance-design.md`

## Global Constraints

- Never promote a reduced finite fixture to an upstream defect or general proof.
- A model/packet string is data, not executable code; no arbitrary eval or shell command.
- A change/deployment permission requires separate independently authenticated authority, so this prototype never grants it.
- Do not alter `research/gap_conditional_cell/cases.json` or its original outcome.
- Keep all generated run outputs outside Git.

## Review Focus

- Python bool `True` mistakenly accepted as an `int`.
- Harmless merge and redundant distinct cache keys falsely reported as defects.
- Same source fields with opposite target labels treated as fixable representation loss.
- A changed source hash or mismatching replay silently accepted as original evidence.
- An incomplete finite dataset or unratified owner intent promoted to a full claim.

---

### Task 1: Finite six-question decision wrapper

**Files:** `research/gap_conditional_cell/six_questions.py`, `tests/test_six_questions.py`.

**Interfaces:** `evaluate_case(case, *, input_types=None, old_type=None, source_bytes=None, source_sha256=None, replay=None)` returns a JSON-serializable record with `checks`, `witness`, `verdict`, and `may_change=False`.

- [x] Write failing tests for genuine collision, benign merge, missing and mismatched types, missing authority, incomplete domain, and unobservable source.
- [x] Run focused pytest; verify failure names the missing interface.
- [x] Implement the minimal wrapper using `structural.assess` and strict basic JSON type descriptors.
- [x] Run focused pytest; verify those cases pass.

### Task 2: Provenance and replay boundary

**Files:** Same as Task 1.

**Interfaces:** SHA-256 comparison of given source bytes and required source digest; trusted callback recomputes each recorded old image with no packet code execution.

- [x] Write failing tests for hash drift, missing source/replay, mismatch, and a true source-replayed witness.
- [x] Run focused pytest; confirm red.
- [x] Implement source/replay verification, full-scope refusal, and explicit conditional labels.
- [x] Run focused tests green.

### Task 3: Reuse and independent baseline

**Files:** `research/gap_conditional_cell/six_questions.py`, `tests/test_six_questions.py`, `research/gap_conditional_cell/SIX_QUESTION_RESULT.md`.

**Interfaces:** `audit_frozen_cases()` reports nine-case historical calibration without promoting an upstream claim; `naive_equality_baseline()` is an explicitly labeled comparator, not an independently informed code reviewer.

- [x] Write failing tests for nine-case replay, finite safe quotient, and comparison of false positives/abstentions.
- [x] Run focused pytest; confirm red.
- [x] Implement a CLI entrypoint with JSON output and the bounded comparison.
- [x] Run focused tests, full project suite, source-derived Open MCT replay if supported; record exact outcomes and limitations.
- [x] Commit the code, tests, and concise evidence note to a new isolated research branch.

**Qualification exception (pre-existing):** `python -m pytest -q` was red
before and after the feature because `lean` is unavailable to the Mathlib
diagnostic/fallback test. Focused gate/source-replay tests are green. See
`research/gap_conditional_cell/SIX_QUESTION_RESULT.md`; no merge/production
certification is authorized by this plan.
