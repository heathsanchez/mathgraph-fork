# P6: sequential native research, with semantic probes and matched memory

Frozen before acquisition and inference, 28 November 2026. Extends the native
authority, literal patch verifier and credential separation of b8a6dd622c45832f6041f0173f9e09b4fea9accb.
P5 established consumer transfer and a conventional-cache tie; neither supplies
evidence of autonomous compounding. This trial can also end in a tie or failure.

## External work and sealed authority

Take the first admissible merged bug fix in each repository, in the exact ordered
pool in prepare.py, until four distinct repositories are admitted. Within each
repository: first 100 most recently updated closed PRs, eligible merged titles,
descending PR number, at most three native candidates. Stop admission after 20
minutes at a candidate boundary. Keep every rejection. At least three tasks are
required before any model call. Never replace tasks based on model outcomes.

Require one bounded changed Python production file, one existing changed test
file, no configuration changes, at least three baseline passes, baseline assertion
failure, and an identical collected test roster passing at the author revision.
Authenticate exact source/test Git blobs. Store original source plus author's
tests, and separately retain the correction. Inference receives original source,
the PR title, baseline diagnostic and coverage; complete author tests and corrected
source stay out of prompts. Published tasks may be in model pretraining. This is
prospective execution, not a claim of newly discovered or globally unseen defects.

## Executed sequence and four arms

For each task, freeze semantic probe code BEFORE proposing any correction. Execute
it on the baseline, then allow at most two fresh-original-source repair proposals.
Each proposal is evaluated on unchanged author tests and the arm's frozen probes.
Native feedback may be used by its own second attempt. No inter-arm feedback until
the episode ends. Afterward make one common learning call from all arms' completed
evidence, before opening the next task to inference. Retain a bounded, source-bound
method containing guidance, semantic-probe recipe and an executable feature guard.

All arms use the same model, reasoning setting, raw completed-episode history and
native tool. The exception is the declared cold ablation, which has no history.

* engine: activate finite-qualified learned methods by their guards.
* memory: receive ALL the same learned methods and raw history; freely choose,
  reconstruct or ignore any method. No prohibition on using guards or probes.
* removal: same engine history and selection, remove the latest active method.
* cold: same current-task budget, no earlier-task evidence or learned method.

Inactive methods add no text to the prompt. At zero methods, all prompts are
identical. Byte-identical prompts share ONE model draw and its attributable cost;
these are not independent replications. Counterbalance arm order by task index.
Later distinct prompts get separate draws; one small stochastic trial cannot
establish a statistically reliable causal effect. Record that limitation even
if the removal arm scores lower.

Each arm/task: one probe call and <=2 repair calls, <=2400 output tokens each.
One common learning call per completed task except the last, <=1800 tokens.
Four tasks imply <=51 distinct API calls and <=120600 requested output tokens;
actual shared-draw savings are recorded. Model gpt-5.6-sol, reasoning low, same as
the previous native trial; this does not claim to benchmark the newest model.
No manual repair, prompt revision, task substitution or outcome-driven rerun.

## Qualification, costs and falsifiers

Learned methods are advisory. Qualify syntax, bounded guidance and probe recipe,
positive match on preceding evidence and zero-failure withdrawal, not universal
semantic validity. Evidence hashes bind all methods to completed receipts. Missing
or changed supports deactivate only dependent methods. Inactive-guidance
noninterference and selective withdrawal have deterministic verifier tests.

Probe code has bounded syntax and no process, network, file or introspection
operations. Run every generated probe and correction in a nonroot, read-only,
network-disabled resource-limited Docker container, with no API or GitHub token.
Only fixed harness code can use the API key in its separate step. Model output
never executes in the API process. Full author tests remain immutable.

Primary result: selected proposals passing the unchanged independently authored test
roster, preserving all baseline passes/skips. Select author-qualified proposals
before unqualified ones, then prefer passing frozen probes, then the later round.
A failed retry cannot erase an earlier author-qualified candidate. All unsuccessful
attempts remain in the learning history. Secondary: also pass generated
probes. After proposals freeze, run each probe against the author's correction:
rejecting that correction is a probe-specificity failure, not an upstream defect.
Do not filter probes or rerun models based on this result. All-arm candidate/probe
cross-checks are deterministic post-outcome diagnostics, not held-out evidence.

Measure acquisition time, each model's actual usage and latency, native execution
time, rejected attempts, probe failures, learning overhead, shared draws and
reviewable receipt volume. No invented dollar conversion or labor saving. Equal
caps do not imply equal actual cost. A tie means no advantage; a higher engine
score is only a bounded candidate effect until independent repeated trials.

Full native tests beyond the admitted module, universal oracle correctness,
unseen-code discovery, accepted upstream repair, long-term economics and general
self-improvement remain UNKNOWN. Save exact source, prompts, model responses,
all per-test verdicts, failures, hashes and cold-replay instructions. No upstream
communication, production change, new repository or deployment.
