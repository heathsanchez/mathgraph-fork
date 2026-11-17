# Distinction-guided LLM repair-selection pilot — 2026-11-17

## Experiment and evidence identity

- **Research question:** Is choosing a correct small repair from prewritten options already easy for a capable LLM, and does an independently grounded missing-distinction diagnosis improve the decision beyond generic review guidance?
- **Frozen case-file commit:** `499f69393f7964562114048570a68bfebf4ccfc3` (before any calls).
- **Exact executing commit:** `63dc14298913188afe30a868c516b0609e67ee0c`.
- **GitHub Actions:** https://github.com/heathsanchez/mathgraph-fork/actions/runs/44062956313 — both inference and independent-scoring jobs SUCCESS.
- **Scored artifact:** https://github.com/heathsanchez/mathgraph-fork/actions/runs/44062956313/artifacts/14318872366 (artifact ZIP SHA-256 `5f5541168cd930f983240841f8336208ee62cc1803938cbd88476d4df73e81e6`, independently rehashed).
- **Model:** `gpt-5.6-sol`; reasoning effort `low`, output cap 220 tokens; 30 completed calls, 6,384 input / 651 output / 7,035 total reported tokens.
- **Dataset:** Eight historically merged external PR repairs and two cases where the input binding/intent policy was not authoritative. Fixed A–E choices and correct labels, deterministic shuffled run order. The model saw only observations/options and optional guidance, never the answer key. Source PRs and outcomes are in `cases.json`.

## Measured paired result

| Arm | Correct / 10 | Correct merged repair / 8 | Correct unknown abstentions / 2 | False accusations on unknowns | Invalid replies |
| --- | ---: | ---: | ---: | ---: | ---: |
| RAW | 9 | 7 | 2 | 0 | 0 |
| GENERAL | 10 | 8 | 2 | 0 | 0 |
| DISTINCTION | 10 | 8 | 2 | 0 | 0 |

The **only paired difference** is NYX-PARQUET: RAW selected E (abstain), GENERAL and DISTINCTION selected D (the historically merged frame-metadata repair). The other nine cases had identical choices in all three arms. No diagnostic-induced harm in this frozen finite cohort.

## Warranted conclusions

- **WARRANTED_BOUNDED:** GPT-5.6 Sol chose the researcher-curated historically accepted repair option on 7/8 merged cases with no special guidance; all eight with either generic review guidance or the specific independently grounded distinction diagnosis.
- **WARRANTED_BOUNDED:** All arms correctly withheld a defect/repair assertion on the two cases with unratified input/intent contracts.
- **BASELINE_TIE:** MathGraph diagnosis showed no incremental decision accuracy over equally available generic engineering review guidance in these ten tasks.
- **UNKNOWN:** Open-ended patch generation, independent native patch correctness, unprompted discovery of missing distinctions, representative detection/false-accusation rates, robustness against model exposure to public PR history, model-to-model transfer, time/cost advantage, general specification adequacy.

## Scientific limits

This is an exploratory retrospective **multiple-choice repair-selection pilot**, **not** a prospective software repair benchmark or random sample. Options were authored after the public fixes were known. The answer key derives from merged PR outcomes and independent researcher judgment, not a fresh owner adjudication, and the scoring job did not replay original native projects. Output answers were **never executed as code**. A good score supports the narrow conclusion that *repair choice from clear options is easy here*, not that an LLM can find the original bug, construct a patch, or safely deploy it.

## Highest-leverage follow-up

Run a prospective, source-native, **open-ended** matched test with the same model, token budget and independent protected regression oracle:

1. Freeze unfamiliar baseline source, authoritative requirement, original protected tests, and matched time/token budgets before inspection.
2. RAW: the model sees unpatched source and original failure only; GENERAL: same plus generic review guidance; DISTINCTION: same plus an **independently established** minimal collision witness, without repair instructions.
3. Require model-authored source patches, then execute them in a separate credential-free sandbox on identical hidden positive/negative native tests, original-to-patch-to-withdrawal controls.
4. Score patch correctness, forbidden changes, justified abstention, model calls/tokens and all-in cost. Include a strong diagnostic-only baseline and a held-out repository.
5. Promote superiority only if differences survive paired testing; otherwise retain **TIE** or **UNKNOWN**.

This run informs the MathGraph strategy: prioritize discovery and independent validation of the consequential residual, not a new specialized LLM repair-choice engine.
