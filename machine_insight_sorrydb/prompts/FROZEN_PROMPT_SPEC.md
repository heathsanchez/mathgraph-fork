# MACHINE INSIGHT × SORRYDB — Frozen Prompt Specification v1

Model: `gpt-5.6-sol`
Reasoning effort: `medium`
Temperature: provider default / not set
Maximum output tokens per model call: 4096
Maximum logical attempts: A=1; B/C/D/shuffled/random=4
Retrieval: none. Source context is deterministic original-project text only: at most 6000 characters before and 6000 characters after the target line.

## System instruction

You are a Lean 4 theorem prover inside a controlled experiment. Produce ONLY the exact Lean code that should replace the target `sorry` token: no Markdown fences, no explanation, no label. You may use declarations already available in the supplied original project context. Never use `sorry`, `admit`, `axiom`, `unsafe`, or any mechanism that bypasses Lean's kernel. The candidate will be independently verified by the official SorryDB verifier. Keep the proof as short and robust as possible.

## Shared first attempt

All conditions receive exactly the same task ID, pinned project/revision metadata, SorryDB goal state, deterministic source context, and system instruction. One physical OpenAI response is generated and independently Lean-verified once. That exact candidate, verifier result, response ID and usage record are logically copied into A/B/C/D/shuffled/random as attempt 1. No condition can diverge before the first verified failure.

## B — Raw retry

Receives its own previous candidate and the ordinary official Lean/SorryDB feedback from that candidate, truncated deterministically at 12,000 characters. It receives no structured residual or repair-family recommendation.

## C — Structured residual

Receives its own previous candidate and a deterministic JSON residual parsed only from the same Lean feedback available to B. It receives no repair-family recommendation. Unsupported residual fields are null or empty.

## D — Machine Insight

Receives its own previous candidate, the same deterministic residual as C, and one deterministic obstruction-driven repair family. On later retries the repair selector switches away from already attempted repair families where possible. It never sees candidates or outcomes from B, C, shuffled, random, another task, or future attempts.

## Shuffled residual control

Receives its own previous candidate plus a residual from another first-attempt failure in the same frozen repo/commit group. The donor proof/candidate is never exposed. Donors are matched on residual family where possible; whether matching succeeded is logged. If no donor exists, a declared `NO_ELIGIBLE_DONOR_IN_GROUP` residual is used rather than inventing evidence.

## Random repair control

Receives its own previous candidate and its own correct structured residual, but the repair family is chosen by a deterministic SHA-256-derived pseudo-random rule independent of outcome.

## Isolation and authority

Only the official SorryDB verifier in the exact original project environment can declare success. `INFRA_ERROR` is a separate terminal state and must not be counted as proof failure. No held-out solution, successful candidate from another condition, future failure, manual theorem-specific hint, or transfer outcome is exposed to any model call.
