# Applicability transfer: prospective native regression test

Frozen before inference on 28 November 2026. This is an engineering experiment,
not a claim of general autonomous invention or proof of repair applicability.

Hypothesis: a retained, finite-qualified applicability condition improves verified
repair success over ordinary adaptive retry and graph-guided correction on later,
independently authored defects under equal model-call and output-token caps.

## Admission and temporal boundary

One exposed training defect: pypa/packaging PR 1531, merge
5a7d3386d2777180a381eb947f21293124ce8df5. It is prior development evidence.
Future cohort is the first admissible defect in each of four distinct repositories
in the exact ordered pool in prepare.py. For each repository, query the first 100
closed PRs sorted by update, consider merged bug-title candidates in descending PR
number, and admit at most three native-layout candidates. Admission stops after
20 minutes at the next candidate boundary. Author fix content is
used only in admission. No selection based on model success. Fewer than three
future repositories means UNKNOWN; do not silently substitute an empty test.

Admission requires exactly one modified production Python file and one existing
modified test file, <=100 source changed lines, <=500 test changed lines, and no
configuration changes. Apply the author's new test file to the first parent of the
merge. Parent must produce assertion failures with >=3 passing cases; author head
must pass the identical test-ID roster and preserve skips. Errors, missing reports,
timeouts and environment failures are UNKNOWN and are retained. Source and test
Git blobs, archives, SHA256s, package versions and full native receipts are saved.

This is a prospective inference holdout; the defects are publicly published, and
pretraining contamination or historical exposure is not ruled out. Test assertions
are the only external intent authority. Full package correctness is not inferred.

## Three matched strategies

All strategies see the same original source, native error diagnostic, exact failing
test excerpt, test-result counts, static call edges and per-function passing/failing
coverage; complete outcome hashes point back to full receipts. The same training
proposal, failures and native verification are supplied to every arm. No author
fix, changed-line oracle or future test outcome enters strategy preparation.

1. Ordinary adaptive diagnosis/retry with a freely learned reflection.
2. Graph-guided diagnosis/correction with a freely learned graph reflection.
3. Retained applicability guard plus learned guidance, with ordinary retry outside
   the guard. The guard is a conjunction of <=4 conditions in the explicit source
   and failure-coverage vocabulary in trial.py. It is data, never arbitrary code.

One preparation call per strategy, max1600 output tokens, one shared training
repair call, max2400 tokens. Every strategy gets <=2 repair calls per future case,
max2400 tokens/call, same model gpt-5.6-sol, reasoning effort low. Stop that arm/case
after a fully verified repair. Counterbalance strategy order by rotating it across
cases. Second attempts see only their own first-attempt receipt. They edit original
source afresh. No cross-strategy feedback or future-driven strategy changes.

Equal total caps, not equal actual spending: report preparation plus inference
input/output tokens, call counts and elapsed times. Shared training is disclosed.
An advantage with higher observed token use does not establish cost improvement.

## Checks and falsifiers

Every proposal is a bounded literal replacement in the admitted production file:
<=4 unique, disjoint replacements, <=100 changed lines, Python syntax valid, no
new imports or privileged introspection. Original author tests remain byte-identical.
Candidate code executes only in a separate token-free native job, in a nonroot,
read-only, network-disabled Docker container with resource limits. API jobs never
execute model-produced code and never receive author fixes or source archives.

The guard must match at least one failure-covered training function and withdraw
all recommendations when its failing-coverage feature is set to zero. Check that
property on every training and future function. Rejected modules get no guard
guidance. This is finite structural qualification, not semantic proof. Withdrawal
controls are feature interventions, not claims that the repair model abstained.

A repair is WARRANTED only for the fixed author-test roster: all baseline failures
now pass, every baseline pass still passes, skips preserved, no test IDs lost/added,
and process exits zero. ABSTAIN is recorded, not scored as repair success.

Primary outcome: verified future cases per arm. Report paired case results and
all failures. A tie or lower guard score means no verified advantage. A higher
score is only CANDIDATE bounded advantage: four cases, one stochastic draw, one
training defect. No significance, general recursion, specification repair, new
primitive invention, or universal novelty claim follows. This graph is syntactic
calls plus measured coverage, not a replication of tool-call dependency graphs.

## Evidence and lineage

Reuses the native-author authority and Docker isolation from the earlier real
investigator (fa24f0dd2a8e5bd37531a671c19dd171ad34d6f7), whose successful
workflow admitted two training cases and zero later cases. That run is not evidence
of transfer. This protocol removes its single-function admission requirement,
corrects the pytoolz repository identity, and sets the minimum holdout before
making any API calls. No research outcome is inferred from workflow success alone.

Full frozen-data and per-stage artifacts preserve source archives and traces.
Portable evidence.zip omits bulky line traces but records their hashes, retains
all test verdicts, prompts/responses, patch proposals, diagnostics, frozen modules,
protocol, harness source, a per-file hash manifest and exact run/source identity.
