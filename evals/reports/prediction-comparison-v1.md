# Prediction tool integration comparison

Five synthetic scenarios compare identical current agent code with the feature off/on.
The real in-process API, agent and registry execute; prediction HTTP is mocked.
This is a controlled feature ablation, not a historical checkout or ML accuracy test.
It does not measure paid LLM quality.

Generated (UTC): `2026-11-20T10:38:51.272091+00:00`. Python: `3.14.3`.

## Results

| Metric | Before: feature off | After: feature on |
| --- | ---: | ---: |
| Expected scenario outcomes | 0/5 | 5/5 |
| Prediction-producing scenarios passed | 0/4 | 4/4 |
| Unavailable-service scenario passed | 0/1 | 1/1 |
| Prediction HTTP calls (mocked) | 0 | 5 |
| Estimated input tokens | 2825 | 6685 |
| Estimated output tokens | 570 | 815 |
| Demo estimated cost (USD) | 0E-8 | 0E-8 |
| Mean in-process request time (ms) | 28.787 | 29.199 |

Outcome conformance includes correct explicit failure handling.
Four scenarios return predictions; the fifth should fail without inventing a score.
Five conforming outcomes do not mean five successful predictions.

## Per-scenario results

| Scenario | Before status | After status | Before pass | After pass |
| --- | --- | --- | --- | --- |
| prediction-low | needs_clarification | completed | False | True |
| prediction-high | needs_clarification | completed | False | True |
| prediction-boundary | needs_clarification | completed | False | True |
| prediction-alternate | needs_clarification | completed | False | True |
| prediction-unavailable | needs_clarification | failed | False | True |

## Interpretation and limits

Feature-off runs decline an unavailable capability; they cannot satisfy these requests.
Feature-on checks cover tool selection, exact inputs, status, score/label provenance,
limitations, and avoiding unsupported fault hypotheses or equipment actions.

All scores are declared fixtures, including the low example resembling the live result.
No XGBoost prediction is computed in this evaluation. Token counts are demo estimates.
Cost is the demo provider's zero estimate; latency excludes an AWS network round trip.
This adds capability, with no claim of token savings or general diagnostic improvement.

The JSON sibling retains inputs, fixtures, actual API responses, checks and hashes.
Existing 30-case baseline/optimized evaluation results remain separate and unchanged.

## Reproduce

```powershell
python -m evals.prediction
```

No EC2, tunnel, API key, or running service is required.
Temporary seeded databases are isolated and removed after each case.
