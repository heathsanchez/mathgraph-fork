# Six-question assurance gate — bounded design

**Intent.** Turn the existing `research/gap_conditional_cell/structural.py`
finite collision gate into an executable, reviewable response to six questions:
recorded type conformance, interface sufficiency, specification correspondence,
meaning loss, evidence scope, and authority to act.

**Scope.** An opt-in, dependency-free Python evaluator of *source-qualified case
packets*, not an autonomous whole-repository bug finder. Reuse the existing
finite structural test and its frozen nine-case dataset unchanged. Accept an
optional real replay callback and exact pinned-source bytes; do not execute
arbitrary strings from a packet. Return distinct findings, uncertainty and
action permission, with a separating witness when justified.

**Goals.** Detect a same-representation/different-required-outcome pair; preserve
safe quotienting, missing types, incomplete domains, source/target
non-identifiability, source drift, missing replay, and unratified authority.
Protect the difference between a conditional technical witness and a binding
engineering interpretation. Produce machine-readable evidence and run local
tests with known positives and negatives across the existing multi-project
fixtures, plus a pinned Open MCT source-derived replay.

**Non-goals.** Do not claim universal type soundness, independently infer an
engineer's intent, call models, modify upstream code, certify production safety,
or measure predictive superiority from retrospective cases.

**Approach.** Extend the existing finite gate with an external typed/provenance
wrapper. This retains the qualified structural core and avoids duplicating an
AST scanner. A textual heat-map approach was rejected by held-out negative
results; an end-to-end multi-language source analyzer is outside this one
bounded experiment. A conventional baseline receives exactly the same finite
input rows and contract; compare its detection and abstention explicitly.

**Anti-goal.** A green local test must never become an authorization to repair,
deploy or assert an upstream defect. Report `UNKNOWN` where requirements,
domain completeness, source behavior or owner permission are unqualified.
