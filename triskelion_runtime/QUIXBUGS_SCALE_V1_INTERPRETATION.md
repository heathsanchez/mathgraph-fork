# Checkpoint 2 interpretation — QuixBugs scale V1

## OBSERVATION

The frozen five-arm experiment completed 175 protected observations over 35 independently authored QuixBugs tasks. The first VERIFIED job attempt failed its River health check before making a model call. Only failed jobs were rerun at the unchanged commit; the final scientific dataset contains zero infrastructure errors.

| Arm | Success | 95% Wilson interval | False activation | Format errors | Output tokens |
|---|---:|---:|---:|---:|---:|
| COLD | 18/35 (51.4%) | 35.6–67.0% | n/a | 6 | 25,789 |
| RAW MEMORY | 2/35 (5.7%) | 1.6–18.6% | n/a | 29 | 43,639 |
| ALWAYS-ON | 10/35 (28.6%) | 16.3–45.1% | 117/175 (66.9%) | 19 | 22,951 |
| VERIFIED | 16/35 (45.7%) | 30.5–61.8% | 6/40 (15.0%) | 4 | 27,602 |
| WRONG-SCOPE | 12/35 (34.3%) | 20.8–50.8% | 40/40 (100%) | 11 | 30,922 |

The predeclared primary cold-improvement gate failed:

`Δsuccess = VERIFIED − COLD = −5.7 percentage points`, conservative Newcombe 95% interval `[-36.5, +26.2]`.

The scope-control gate passed:

`ΔFA = ALWAYS-ON − VERIFIED = +51.9 percentage points`, conservative Newcombe 95% interval `[+30.5, +66.3]`.

VERIFIED also exceeded ALWAYS-ON by 6 tasks and WRONG-SCOPE by 4 tasks. The wrong-scope success difference is `+11.4pp` in VERIFIED's favour, with a wide post-hoc Newcombe interval `[-20.4, +41.0]`.

The frozen router selected 40 capability-task pairs: 34 were labelled applicable and 6 false, giving 85.0% activation precision. It missed 24 of 58 labelled applicable pairs, giving 58.6% activation recall.

By frozen seven-task category, VERIFIED versus COLD was: composition `4 vs 2`, direct applicability `2 vs 4`, near-miss `4 vs 5`, transfer `5 vs 5`, unrelated control `1 vs 2`.

Post-hoc paired accounting, not a predeclared gate, found VERIFIED gained six tasks and lost eight relative to COLD (exact two-sided McNemar `p=0.791`); gained twelve and lost six relative to ALWAYS-ON (`p=0.238`); and gained eight and lost four relative to WRONG-SCOPE (`p=0.388`).

## INTERPRETATION

**REJECTED — meaningful advantage over cold on this natural source-distinct stream.** The point estimate favours COLD, and uncertainty is wide. Checkpoint 1's one-task V2 advantage does not survive this scale test.

**SUPPORTED — retention is not activation.** Exposing all five retained critics produced 66.9% false activation and only 10 successes. The scoped runtime reduced false activation to 15.0% and recovered six successes. The false-activation confidence interval excludes zero by a substantial margin.

**SUPPORTED, bounded — scope metadata has functional value distinct from the artifact registry.** The registry and critic artifacts were held fixed while deliberately wrong routing reduced success from 16 to 12 and raised false activation from 15% to 100%. The success difference is directionally correct but individually underpowered.

**REJECTED — raw episodic memory as a competitive arm under this interface.** It scored 2/35, used 58.2% more output tokens than COLD, and produced 29 format errors. This is partly an interface/context-overload result, not proof that all raw-memory methods are intrinsically poor.

**CANDIDATE — capabilities preferentially help compositional repairs.** VERIFIED doubled composition success from 2/7 to 4/7, but the category is too small and was manually curated before calls. This is a target for a larger, independently labelled holdout, not a claim.

The main obstruction is now specific: the runtime controls harmful overactivation, but the five broad critics and source-only router do not add enough correct task competence to beat the frozen model cold. Router recall is only 58.6%, and even correctly routed declarative critics sometimes perturb already-correct cold proposals. The next change should therefore not add more mechanisms. It should improve admitted capability quality and applicability using source-distinct admission evidence, while preserving this exact scale suite as a protected regression set.

Checkpoint classification:

- `PASS — source-distinct scale execution and evidence integrity`;
- `SUPPORTED — scoped activation beats always-on and wrong-scope exposure`;
- `REJECTED — runtime beats cold on natural package tasks`;
- `OPEN — admitted executable capabilities that add competence without proposal interference`.
