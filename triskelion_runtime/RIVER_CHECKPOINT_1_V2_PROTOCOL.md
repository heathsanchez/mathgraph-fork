# River Checkpoint 1 V2 — precommitted response normalization

Protocol: `TRISKELION_RIVER_CHECKPOINT_1_V2`. Seed: `20260816`.

V1 is immutable and remains the primary negative/mixed result. V2 changes exactly two frozen fields before making any new model call:

1. The per-task seed base changes from `20260815` to `20260816`, ensuring fresh samples.
2. Response normalization examines every fenced block in output order and selects the last block that parses as Python and defines the requested top-level function. If none qualifies, the response fails. This rule is deterministic, model-independent, and applied identically to all arms.

The model, temperature `0.0`, 512-token maximum, six-task corpus, task order, prompts, capability registry, scope router, artifact execution order, verifier, four arms, and primary gates are unchanged from V1.

The motivation is declared from V1's measured obstruction: 16/24 outputs failed the exact-one-block contract because of multiple blocks, truncation, or non-code fenced material. V2 tests whether capability effects remain after normalizing this output-interface failure. It does not overwrite or reinterpret V1 verdicts.

Primary gates remain:

- VERIFIED > COLD protected success.
- VERIFIED > ALWAYS-ON protected success.
- false activation VERIFIED < ALWAYS-ON.
- zero infrastructure errors.

Output-format failures, latency, and output tokens are recorded per arm.
