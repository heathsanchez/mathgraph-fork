# Gap-conditional structural Cell / LLM experiment — final bounded verdict

**17 November 2026 · read-only model proposals, exact GitHub Actions replay**

## Objective

Test the smallest workable division between structural requirements and language-model invention:

- **Structural, no LLM:** source/claim authority check, incomplete-domain refusal, source-level impossibility, finding a protected same-observation/different-outcome collision, bounded native-equivalence verification, safe code grammar, receipt/source binding, and fail-closed UNKNOWN.
- **LLM only for eligible gaps:** propose an anonymous, pure new representation expression without any repair-category menu; or explicitly request a genuinely new semantic primitive.
- **Independent consumer:** validate expression-derived equivalence classes without executing LLM-generated Python and without access to the OpenAI API secret.
- **Matched counterfactual:** run the same model on *every* case, to measure what a structural gate saves.

## Immutable evidence

- Source/case roster first frozen at [commit `4d441e11`](https://github.com/heathsanchez/mathgraph-fork/commit/4d441e11ba4db7ea18ba8f1f237fe4a604b611f1), before model inference. Nine cases, 385 frozen source records. Five eligible collisions; four structural stops.
- Original exact executing source: [`7c66e67e`](https://github.com/heathsanchez/mathgraph-fork/commit/7c66e67ee3ba0e2c6ef9da8cac5041cf489b6a63). [Original experiment `44067908479`](https://github.com/heathsanchez/mathgraph-fork/actions/runs/44067908479) both jobs SUCCESS: structural test, 14 OpenAI API calls, separate credential-free scoring and original raw artifacts.
- Original scored result erroneously used `WARRANTED_FROZEN_FINITE_KERNEL` for a matching expression on a *non-complete* three-row case. This is **superseded by the scope correction** below. It is not evidence of an LLM semantic failure, only of a scorer label that could invite overinterpretation.
- [Corrected authority/coverage verifier `87b90e13`](https://github.com/heathsanchez/mathgraph-fork/commit/87b90e135ac1688fb503b3bedb774b0b1d3da935), [scorer correction `d237e04c`](https://github.com/heathsanchez/mathgraph-fork/commit/d237e04c5d49149105d535c5203db457c73101f4).
- [Zero-API-call exact original-response requalification `44068509933`](https://github.com/heathsanchez/mathgraph-fork/actions/runs/44068509933), SHA [`fb4c2135`](https://github.com/heathsanchez/mathgraph-fork/commit/fb4c2135559c690b78d96c3517071cab4934a7eb), successful independent job. [Corrected full artifact #14320768423](https://github.com/heathsanchez/mathgraph-fork/actions/runs/44068509933/artifacts/14320768423) ZIP SHA-256 `1f09232d40070eb7d49c87f874a0318f9d3f053f65639e097e74f74b184c2974` independently rehashed. Reused the immutable original model proposals.
- Model `gpt-5.6-sol`, effort low; actual 14 model calls and 6,454 total tokens, all from original run. No model output executed by Python `eval` or `exec`.

## Exact outcomes

| Case | Structural gate | LLM proposal on eligible gap | Finite independent check |
| --- | --- | --- | --- |
| L4YAML key/embedded NUL | ELIGIBLE_GAP | `s["key"]` | 12/12, target kernel matched |
| Nyx frame identity | ELIGIBLE_GAP | `(s["frame"], s["coords"])` | 9/9, target kernel matched |
| CySat same-cell history | ELIGIBLE_GAP | `abs(s["current"] - s["previous_same_cell"]) > 5` | 81/81, target kernel matched |
| Ogma typed threshold | ELIGIBLE_GAP | `s["temperature"] < 120` | 256/256, target kernel matched |
| Python Unicode casefold | ELIGIBLE_GAP | `NEED_NEW_PRIMITIVE` | UNKNOWN, no unqualified replacement |
| Closed finite parity | SUFFICIENT_FROZEN_FINITE | **No call** | No new bridge required |
| Open unbounded domain, three samples | UNKNOWN_INCOMPLETE | **No call** | No general sufficiency warrant |
| Unratified R2U2 header contract | UNKNOWN_AUTHORITY | **No call** | Owner must establish binding semantics |
| Invisible owner intent, same raw source | UNOBSERVABLE_FROM_SOURCE | **No call** | Impossible to decide from exposed fields alone |

The typed-temperature expression legitimately removes the branch `temperature > 180` **only within the declared signed Int8 input domain**. It is not a universal simplification if the input type or domain later changes. Source and semantic hashes must therefore invalidate reuse after a type change.

## Paired arms

| Metric | ALWAYS (counterfactual) | GAP_ONLY (proposed method) |
| --- | ---: | ---: |
| Total model calls | 9 | 5 |
| Verified finite-gap closures / 5 eligible | 4 | 4 |
| Unresolved grammar expansions / 5 | 1 | 1 |
| Non-gap model calls | 4 | 0 |
| API input tokens | 3,272 | 2,178 |
| API output tokens | 606 | 398 |
| API total tokens | 3,878 | 2,576 |
| Explicit false finite warrants after corrected replay | 0 | 0 |
| Sample-only matches on incomplete cases | 1 | 0 |

**Measured:** 44.4% fewer calls and 33.6% fewer API tokens, with the *same four* finite expression qualifications. Distinct prompts mean token savings are descriptive, not an identical-prompt causal isolator. No evidence of greater repair accuracy from supplying the structural collision witness: both arms matched on every eligible task.

**Important failure/repair lineage:** The original always-call arm proposed `s["x"]` for an unbounded-domain requirement after seeing three confirming cases. That is a plausible expression and may indeed be correct, but the finite packet cannot independently establish it for all integers. The corrected verifier emits `CONSISTENT_SAMPLES_ONLY`, not a full-domain warrant. Structural STOP avoids unnecessary calls and premature promotion. The original raw result remains archived; the corrected result supersedes only its status classification.

## What is warranted and what is not

**WARRANTED_LOCAL_FINITE:** deterministic gate classified exactly five old-interface collisions, one complete finite no-gap, one incomplete no-gap, one missing-owner authority and one source-information impossibility. The LLM proposed four anonymous expressions whose output kernels exactly equal the independently frozen protected target kernels *across the enumerated rows*. The gate refused all four noneligible model calls; code safety did not rely on evaluating arbitrary generated code. Corrected independent scoring passed.

**CANDIDATE:** A useful reusable `source → fiber collision → candidate expression/primitive request → typed qualified Cell` interface to actual MathGraph Check, with sourced model/requirement authority and live revocation.

**UNKNOWN:** general source-native production correspondence; original upstream repository behavior re-executed on this new run; independently ratified owner intent; domain-complete proof outside finite frozen rows; semantic invention of a novel primitive; general Unicode casefold primitive authorization; physical sensor side effects; future-policy completeness; actual Unit/Cell integration; held-out prospective independent software; comparison with a fully informed conventional static compiler; comparative commercial or accuracy advantage. The four historical public PR patterns motivated **reduced fixtures**. The model was not discovering the original bugs.

**REJECTED AS EVIDENCE OF SUPERIORITY:** Claim that MathGraph diagnosis gave better gap completion than the LLM with the ordinary requirement; the completed finite repairs were 4/5 in both arms. The demonstrated value of structure here is **routing, scope control, prevention of premature warrant, and less model work**.

## Highest-leverage next experiment

1. Reuse the same *existing* structural gate and candidate proposal interface, not another architecture.
2. Freeze one genuinely unopened independently authored source/requirement and native positive and negative controls, including an authoritative source-to-outcome oracle.
3. LLM proposes one source-grounded observation or asks for one missing primitive only if a source-qualified fiber collision exists. No preset repair categories or programmer-chosen downstream repair after seeing the result.
4. Enroll the candidate into the **actual** typed MathGraph Cell/Unit, retaining source, verifier, types, admissibility, allowed effects, witness, and dependent revocation. Run real native original/repair/withdrawal tests in a credential-free sandbox.
5. Compare an equally informed general LLM, conventional static/semantic evaluator, and gated approach under identical source access and full cost. Require a causal held-out outcome change before claiming general capability advantage.

**Bottom line:** Make authority, nonidentifiability, completeness, type safety, native verification and revocation structural. Let the LLM work only on residuals where new expressible observations are needed. Treat proposals, including requests for new primitives, as candidates until an independent boundary admits them.
