# Six-question assurance gate — source-pinned bounded experiment

**18 November 2026 · bounded public research receipt**

## Question and decision

Can the existing finite distinction checker be turned into one executable
six-question assurance procedure, while preserving the independent boundaries
for types, interface identity, specification intent, meaning, evidence and
authority? **Yes, for admitted finite case packets and one pinned original-class
replay.** Whether it *reliably finds unknown consequential bugs across unrelated
repositories* remains **UNKNOWN**; this is not a prospective performance study.

## Code and deliberately restricted contract

- `six_questions.py` reuses the unchanged finite `structural.assess` gate and
  returns six separate JSON statuses, a separating witness when known, a
  conservative verdict, and `may_change: false` under every path.
- The input type test validates only recorded top-level JSON field types; it
  does **not** establish implementation-wide type soundness.
- Specification correspondence is at most `DECLARED_CONTRACT_ONLY`. Source
  bytes and replay callbacks are caller-provided and not authenticated by the
  general evaluator. Absent/changed source, missing replay, missing type
  contract, unratified owner, incomplete world and unobservable intent are
  not promoted to positive assurance.
- The record relation is **one-way for safe reuse**: same stored observation
  must not merge different protected decisions. Two separate keys for
  equivalent outcomes are not automatically a defect. Stateful false splits
  require an independent behavioral dependency.
- Nothing automatically changes source, approves a repair or deploys code.

## Qualification 1: frozen multi-project calibration (not source-native)

Original nine-case file remains unchanged, SHA-256
`c9c0867547e621ae49f0df39ccc84e7032a7033ed71835f9b2782cd88a876bd6`.
Cases are reduced historical patterns motivated by L4YAML, Nyx, CySat, Ogma,
Unicode, R2U2 and finite controls, not native reruns of those projects.

| Original structural status | Cases |
| --- | ---: |
| ELIGIBLE_GAP | 5 |
| SUFFICIENT_FROZEN_FINITE | 1 |
| UNKNOWN_INCOMPLETE | 1 |
| UNKNOWN_AUTHORITY | 1 |
| UNOBSERVABLE_FROM_SOURCE | 1 |

All nine six-question wrappers withhold change permission; none promotes a
source-native claim. A weak identity-only collision baseline emits **7 alerts**
without distinguishing their decision relevance. An equally informed
independently coded O(n²) pairwise oracle finds **5/5** eligible distinctions
on the seven source-identifiable/declared finite cases; the structural gate
also finds **5/5**. This is a **BASELINE_TIE**, not comparative superiority.

Additional exhaustive finite control: all **256** functions from four source
states to two old images and two protected outcomes agreed with the independent
pairwise collision oracle. This is a bounded finite relation, not all software.

## Qualification 2: original pinned NASA Open MCT classes

Git source: [NASA Open MCT at e09bfaf4](https://github.com/nasa/openmct/tree/e09bfaf47856b2b7ae2ea74334800b26fd27a41e), with
`TelemetryAPI.js` SHA-256
`95c39cfe100fb27724927976a1cc50a0576becb28e9f70e58c159803bc827802`.
The replay loads original `TelemetryAPI`, `StateGeneratorProvider` and
`object-utils` source unchanged. Only unrelated imports and timer environment
are stubbed. It checks source commit and exact byte hashes before execution.

Two distinct numeric-string filters parse to required states **0** and **1**.
The original cache creates **one provider subscription** for both, delivering
**[0] to each subscriber**. An independently subscribed distinct-domain control
receives **[1]**, and identical-options reuse remains working. The six-question
relation gate returns `WARRANTED_BOUNDED_CONDITIONAL_RELATION` for those rows,
while still returning `NO_CHANGE_PERMISSION`. The intended filter separation
has supporting [Open MCT issue #7933](https://github.com/nasa/openmct/issues/7933).

| Six-question result on source-replayed rows | Recorded status |
| --- | --- |
| Type correctness (recorded fields only) | `RECORDED_TYPES_CONFORM` |
| Interface correctness | `COUNTEREXAMPLE_CONDITIONAL` |
| Specification adequacy | `DECLARED_CONTRACT_ONLY` |
| Meaning gap | `CONSEQUENTIAL_COLLISION` |
| Evidence boundary | `DECLARED_BYTES_AND_REPLAY_MATCH` |
| Authority to change | `NO_CHANGE_PERMISSION` |

**Boundary:** Original-class replay with controlled imports/timers, not full
Karma/Jasmine/E2E, deployed telemetry, arbitrary options equivalence or owner
adjudication. Whether these unusual but code-admitted numeric filter spellings
are in the supported public subscription contract remains UNKNOWN. No upstream
issue, PR, source mutation or repair authorization follows from this run.

## Reproduction

```bash
python -m pytest -q tests/test_six_questions.py
python -m research.gap_conditional_cell.six_questions --frozen
# With exact, unmodified Open MCT checkout at e09bfaf47856b2b7ae2ea74334800b26fd27a41e:
OPENMCT_PINNED_CHECKOUT=/path/to/openmct python -m pytest -q tests/test_openmct_source_replay.py
```

Opt-in CI workflow `.github/workflows/assurance-six-gate.yml` performs the
source-pinned public checkout and exercises both focused suites without model
calls. **Local focused suite:** 23/23 PASS with the source checkout supplied.
**Local whole-repository suite:** starting checkout 1,302 PASS / 1 FAIL;
after these tests were added 1,325 PASS / 1 FAIL. Both failed in the same
`tests/test_mathlib_module_verification.py::test_failed_diagnostics_and_fallback`
assertion; this environment has no `lean` executable, so the expected failed
Lean-check diagnostic was absent. The full suite is **NOT GREEN**, though no
additional failing test was observed. Do not count this as a new
assurance-gate regression or claim whole-repository qualification.

## Residual and decisive next experiment

**Missing:** A prospectively nominated gap on a genuinely unopened repository,
with a source-exact causal extractor, an independently admitted requirement
oracle, verified native behavior, and a fully informed conventional baseline
given equal source access. The present evaluator verifies *supplied* candidate
relations; it does not autonomously discover candidate edges in arbitrary code.

**Next cheapest test:** Freeze a source-to-sink trace extractor (lossy mapping →
identity-dependent reuse → consequential consumer), its top-three nominations,
source/owner question, and an informed LOC/source-review baseline *before*
opening another repository. Run exact native positive and negative controls,
preserve misses and ties, and promote only bounded source-replayed evidence.
Permission to change remains an independent owner decision.
