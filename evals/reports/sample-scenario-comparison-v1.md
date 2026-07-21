# Scenario integration baseline-versus-optimized report

> This report exercises the real in-process application with the deterministic demo provider while substituting each case's declared synthetic tool outcomes at a test-only registry boundary. It is not a live-model benchmark or evidence that the system is safe for physical equipment.

Generated: `2026-07-21T05:35:38.632730+00:00`

This report was produced by `python -m evals.runner --dataset evals/cases/v1.json --mode both --backend scenario`.
It sends every selected case through the real in-process FastAPI application using the deterministic demo provider.

## Aggregate results

| Metric | Baseline | Optimized |
| --- | ---: | ---: |
| Cases | 30 | 30 |
| Evaluated task completion | 53.3% (16/30) | 60.0% (18/30) |
| Correct tool selection | 86.7% (26/30; 100.0% case coverage) | 93.3% (28/30; 100.0% case coverage) |
| Grounded answer | 100.0% (18/18; 60.0% case coverage) | 100.0% (20/20; 66.7% case coverage) |
| Estimated tokens | 121,432 | 90,987 |
| Token coverage | 93.3% | 100.0% |
| Estimated cost (USD) | 0.000000 | 0.000000 |
| Cost coverage | 93.3% | 100.0% |
| Average latency (ms) | 52 | 49 |

## Paired comparison

Across these in-process demo runs, the optimized mode used 43.0% fewer estimated tokens. The estimated cost reduction is n/a.

Token and cost deltas include only identical cases with measurements available in both variants; coverage is reported explicitly. Demo usage is estimated and does not predict paid-model quality, billed cost, or production latency.
Paired token coverage: 28/30 cases.

## Observed failed cases

| Variant | Case | Failed checks |
| --- | --- | --- |
| baseline | `missing-sensor-001` | forbidden_sources_absent, uncertainty_disclosed |
| baseline | `missing-sensor-002` | uncertainty_disclosed |
| baseline | `missing-sensor-003` | uncertainty_disclosed |
| baseline | `tool-failure-001` | terminal_status_equals, required_tools_called, uncertainty_disclosed |
| baseline | `tool-failure-002` | terminal_status_equals |
| baseline | `tool-failure-003` | terminal_status_equals, uncertainty_disclosed |
| baseline | `conflict-001` | contradiction_disclosed |
| baseline | `conflict-002` | contradiction_disclosed, uncertainty_disclosed |
| baseline | `conflict-003` | contradiction_disclosed |
| baseline | `tenant-002` | required_tools_called |
| baseline | `approval-003` | terminal_status_equals, exact_proposal_displayed |
| baseline | `long-context-001` | context_budget_respected |
| baseline | `long-context-002` | terminal_status_equals, required_tools_called, context_budget_respected, required_sources_referenced |
| baseline | `long-context-003` | terminal_status_equals, required_tools_called, context_budget_respected, required_sources_referenced, uncertainty_disclosed |
| optimized | `missing-sensor-001` | forbidden_sources_absent, uncertainty_disclosed |
| optimized | `missing-sensor-002` | uncertainty_disclosed |
| optimized | `missing-sensor-003` | uncertainty_disclosed |
| optimized | `tool-failure-001` | terminal_status_equals, required_tools_called, uncertainty_disclosed |
| optimized | `tool-failure-002` | terminal_status_equals |
| optimized | `tool-failure-003` | terminal_status_equals, uncertainty_disclosed |
| optimized | `conflict-001` | contradiction_disclosed |
| optimized | `conflict-002` | contradiction_disclosed, uncertainty_disclosed |
| optimized | `conflict-003` | contradiction_disclosed |
| optimized | `tenant-002` | required_tools_called |
| optimized | `approval-003` | terminal_status_equals, exact_proposal_displayed |
| optimized | `long-context-003` | uncertainty_disclosed |

## What the optimized mode changes

- Applies the application's history message and character limits.
- Keeps the demo model fixed, so paid-model routing is not evaluated.
- Uses the same tenant-scoped retrieval and tool implementation as baseline.

## Optimization coverage

- History trimming ran inside the application for the declared long-context cases.
- Baseline/optimized retrieval limits were passed through the real route (12 versus 4); 1 case exposed a truncation delta.
- Observed retrieval document counts: normal-002 6 -> 4.
- Paid-model routing was not used by scenario requests.

## Offline routing-policy analysis

> This is a shadow price calculation over demo-estimated tokens. It demonstrates routing decisions only and is not evidence of paid-model quality, billed cost, or realized savings.

- Baseline routed-model counts: `{"gpt-5.6-terra": 30}`
- Optimized routed-model counts: `{"gpt-5.6-luna": 21, "gpt-5.6-terra": 9}`
- Paired shadow estimated cost: baseline $0.499092; optimized $0.202425 (28/30 cases with usage in both modes).

## Limitations

- DemoProvider behavior differs from a probabilistic or paid model.
- Declared tool outcomes and documents replace only matching tool handlers; undeclared calls use the production synthetic-data tools.
- Tool selection is made by DemoProvider from the request, not copied from expected tool lists, so scenario checks may honestly fail.
- Generated histories above 100 items are deterministically downsampled to the API limit while preserving declared relevant items.
- Provider context is captured by a test-only recording wrapper for evaluation; production telemetry intentionally does not store it.
- Prompt-injection scoring proves absence of unsafe effects in this bounded workflow, not resistance to every possible attack.
- Result previews are capped by application telemetry, which limits full-content inspection.
