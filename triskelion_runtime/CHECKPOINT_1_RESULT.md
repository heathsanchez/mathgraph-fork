# River Checkpoint 1 — interpretation

## Observation

GitHub Actions run `31837457057`, attempt 2, completed successfully on frozen commit `af28ccc908b19ebf1a63b981f15859a8ea4be49b`. The secret preflight, runtime tests, 24 River calls, verification, and evidence upload all completed with zero infrastructure errors.

The frozen model was `Qwen/Qwen3.5-9B`, temperature `0.0`, maximum 512 output tokens, with protocol seed `20260815`.

| Arm | Protected success | False activation | Output-format failures | Mean call latency | Output tokens |
|---|---:|---:|---:|---:|---:|
| COLD | 2/6 | 0% | 2/6 | 3,989.645 ms | 1,909 |
| RAW MEMORY | 1/6 | 50.0% | 4/6 | 3,931.068 ms | 3,072 |
| ALWAYS-ON | 0/6 | 66.7% | 6/6 | 3,341.792 ms | 1,572 |
| VERIFIED SCOPED | 2/6 | 0% | 4/6 | 3,435.641 ms | 1,502 |

Frozen gates:

- `VERIFIED > ALWAYS_ON`: passed.
- `VERIFIED > COLD`: failed (2/6 versus 2/6).
- `false activation VERIFIED < ALWAYS_ON`: passed (0% versus 66.7%).
- zero infrastructure errors: passed.

The evidence artifact is `TRISKELION_RIVER_CHECKPOINT_1_RESULT.zip`, GitHub artifact `9233495130`, digest `sha256:2df0db8cf0ece6fcb356f3f2586ca56a14ff95c557f73fd5d39bb8bf44649980`.

## Interpretation

This run does not support the claim that the frozen neural model plus runtime improves verified task success over the same cold model. It does support, on this bounded suite, the narrower retention-versus-activation claim: verified scope prevented false activation and outperformed exposing every capability.

Response-contract compliance is a measured obstruction, not an infrastructure failure. Sixteen of 24 responses failed the frozen one-code-block parser, often because the model emitted multiple blocks, an incomplete block at the 512-token limit, or non-code material inside a fence. Because the parser and token limit were frozen, these remain task failures in V1. Any more permissive extraction or larger token budget must be a separately declared protocol revision and may not replace this result.

The low sample count and single sample per cell do not justify a strong general claim. Checkpoint 1 V1 is retained as a mixed/negative result.
