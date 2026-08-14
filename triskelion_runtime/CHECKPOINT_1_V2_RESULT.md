# River Checkpoint 1 V2 — interpretation

## Observation

GitHub Actions run `31839983874` completed successfully from precommitted commit `6193dea87a125103b67ee1669f42fcba8ca7bb73`. All 24 fresh River calls ran with zero infrastructure errors.

| Arm | Protected success | False activation | Output-format failures | Total latency | Output tokens |
|---|---:|---:|---:|---:|---:|
| COLD | 3/6 | 0% | 0/6 | 20,554.082 ms | 1,913 |
| RAW MEMORY | 2/6 | 50.0% | 2/6 | 20,357.137 ms | 3,072 |
| ALWAYS-ON | 1/6 | 66.7% | 5/6 | 16,790.750 ms | 1,327 |
| VERIFIED SCOPED | 4/6 | 0% | 2/6 | 18,334.522 ms | 1,976 |

All four frozen gates passed: VERIFIED exceeded COLD and ALWAYS-ON, VERIFIED false activation was lower than ALWAYS-ON, and infrastructure errors were zero.

The evidence artifact is GitHub artifact `9234214098`, digest `sha256:facabdc8945e376db5fe76c8420b770b8c2e2453af68e99f141062522641d5f8`.

## Interpretation

Checkpoint 1 V2 supports the bounded product claim that the same frozen model with verifier-scoped capabilities can outperform the same model cold and with all capabilities exposed. The effect is small versus COLD (one additional task out of six), while the scope advantage over ALWAYS-ON is larger.

This does not erase V1. V1 remains a failed primary-gate run under its stricter response contract. V2 is a separately precommitted protocol motivated by V1's measured interface obstruction.

A diagnostic artifact-only ablation on the two successful positive VERIFIED responses did not restore failure: the model had already encoded the visible manifest's behavior in its proposed source. Therefore this run establishes a causal effect of the capability intervention as a whole, but does not establish that executable artifact application, rather than manifest exposure, caused those two successes. A separately frozen causal decomposition is required.

The sample is too small for a broad or statistically stable claim. Status: **SUPPORTED on bounded V2**, pending repeated seeds, independently authored package tasks, and intervention decomposition.
