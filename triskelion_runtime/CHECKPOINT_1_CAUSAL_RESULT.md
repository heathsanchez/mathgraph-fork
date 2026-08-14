# River Checkpoint 1 causal decomposition — interpretation

## Observation

GitHub Actions run `31841297057` completed eight River calls with zero infrastructure errors. The artifact is GitHub artifact `9234765855`, digest `sha256:965fe5db9e5e44c15fe4c566bd0aa762fa04812242800b997ee934d9ebce800b`.

| Intervention | Protected success |
|---|---:|
| NONE | 0/2 |
| MANIFEST_ONLY | 2/2 |
| ARTIFACT_ONLY | 1/2 |
| FULL | 2/2 |

For `acquire_ratio_zero`, NONE and ARTIFACT_ONLY returned byte-identical model output. NONE failed because the proposal raised `ValueError` at zero; applying the executable capability to the identical proposal passed. This is one valid executable-artifact causal closure.

For `transfer_average_zero`, NONE and ARTIFACT_ONLY also returned byte-identical output. Both failed because the model changed integer division into `total / len(items)`; the zero-guard artifact correctly did not repair this different semantic error. MANIFEST_ONLY and FULL both passed.

The paired-output gate failed overall because the supposedly identical MANIFEST_ONLY and FULL prompt/seed calls for `transfer_average_zero` returned different response hashes. River's seed did not guarantee byte-identical generation across those repeated calls. No incremental artifact attribution is made from that pair.

## Interpretation

The result supports two distinct mechanisms inside the capability object:

1. Executable application can causally close a failure while holding the model proposal byte-identical, proven on the acquisition task.
2. Manifest exposure can steer the frozen model away from an upstream semantic error that the narrow executable artifact cannot repair, supported on the source-distinct transfer task.

FULL succeeded on both tasks while NONE failed both, but the sample is only two tasks. ARTIFACT_ONLY did not pass both tasks, and no incremental value beyond MANIFEST_ONLY was established. The correct status is mixed bounded support, not a general causal claim.

River latency and seed nondeterminism are now recorded infrastructure properties. Future paired experiments require returned-output matching or a provider with deterministic replay/cache identifiers.
