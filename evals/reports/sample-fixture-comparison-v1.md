# Synthetic fixture baseline-versus-optimized report

> This report validates the fixture contract and deterministic accounting only. It is not evidence of application or model accuracy, safety, latency, or savings.

Generated: `2026-07-21T05:35:15.370242+00:00`

This report was produced by `python -m evals.runner --dataset evals/cases/v1.json --mode both --backend fixture`.
It replays the dataset contract without calling the application or a model.

## Aggregate results

| Metric | Baseline | Optimized |
| --- | ---: | ---: |
| Cases | 30 | 30 |
| Evaluated task completion | 100.0% (30/30) | 100.0% (30/30) |
| Correct tool selection | 100.0% (30/30) | 100.0% (30/30) |
| Grounded answer | 100.0% (30/30) | 100.0% (30/30) |
| Estimated tokens | 221,643 | 38,352 |
| Token coverage | n/a | n/a |
| Estimated cost (USD) | 0.735607 | 0.189787 |
| Cost coverage | n/a | n/a |
| Average latency (ms) | unavailable | unavailable |

## Paired comparison

Within this deterministic estimator, the optimized fixture uses 82.7% fewer estimated tokens. The estimated cost reduction is 74.2%.

The deltas are outputs of a deterministic fixture estimator. They do not measure or predict live application, provider, or model performance.


## What the optimized mode changes

- Routes controlled terminal paths to the configured smaller model.
- Accounts for relevant chunks rather than a whole-document envelope.
- Retains only declared relevant items from generated long context.
- Uses a smaller structured-output allowance.

## Limitations

- Case passes show that the fixture replay can satisfy its own declared checks; they do not score the application.
- Token counts are deterministic estimates, not provider-reported usage.
- Cost values are estimates derived from a dated pricing snapshot and are not invoices.
- Latency is unavailable because the runner makes no application, tool, network, or model call.
- A live or recorded-trace profile must be run before making product-quality or savings claims.
