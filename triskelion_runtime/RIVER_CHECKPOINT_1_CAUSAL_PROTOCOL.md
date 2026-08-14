# River Checkpoint 1 — causal intervention decomposition

Protocol: `TRISKELION_RIVER_CHECKPOINT_1_CAUSAL_V1`. Seed base: `20260817`.

Purpose: separate the effect of capability-manifest exposure from executable artifact application on the acquisition task and untouched source-distinct transfer task.

For each task, run four interventions with the same frozen `Qwen/Qwen3.5-9B`, temperature `0.0`, maximum 512 tokens, V2 response normalizer, public example, and protected verifier:

- NONE: no manifest, no artifact.
- MANIFEST_ONLY: scoped manifest visible, no artifact.
- ARTIFACT_ONLY: no manifest, executable artifact applied.
- FULL: scoped manifest visible and executable artifact applied.

The seed is identical across the four interventions for a task. NONE and ARTIFACT_ONLY have byte-identical prompts and must return byte-identical model outputs. MANIFEST_ONLY and FULL likewise must return byte-identical outputs. If either equality fails, causal attribution is invalid rather than silently accepted.

Frozen gates:

1. paired response hashes are identical for both prompt-matched pairs on both tasks;
2. zero infrastructure errors;
3. ARTIFACT_ONLY passes both tasks;
4. FULL passes both tasks;
5. at least one task fails under NONE but passes under ARTIFACT_ONLY, establishing executable-artifact causal closure;
6. at least one task fails under MANIFEST_ONLY but passes under FULL, establishing incremental artifact value beyond manifest exposure.

Failure of gate 6 is informative: it means manifest exposure alone was sufficient on these samples.
