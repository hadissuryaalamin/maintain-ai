# Demo integration baseline-versus-optimized report

> This report exercises the real in-process application with the deterministic demo provider and synthetic data. It is not a live-model benchmark or evidence that the system is safe for physical equipment.

Generated: `2026-07-21T05:35:37.693918+00:00`

This report was produced by `python -m evals.runner --dataset evals/cases/v1.json --mode both --backend demo`.
It sends every selected case through the real in-process FastAPI application using the deterministic demo provider.

## Aggregate results

| Metric | Baseline | Optimized |
| --- | ---: | ---: |
| Cases | 30 | 30 |
| Evaluated task completion | 40.0% (12/30) | 40.0% (12/30) |
| Correct tool selection | 86.7% (26/30; 100.0% case coverage) | 90.0% (27/30; 100.0% case coverage) |
| Grounded answer | 77.8% (14/18; 60.0% case coverage) | 73.7% (14/19; 63.3% case coverage) |
| Estimated tokens | 146,369 | 93,632 |
| Token coverage | 93.3% | 96.7% |
| Estimated cost (USD) | 0.000000 | 0.000000 |
| Cost coverage | 93.3% | 96.7% |
| Average latency (ms) | 36 | 34 |

## Paired comparison

Across these in-process demo runs, the optimized mode used 43.4% fewer estimated tokens. The estimated cost reduction is n/a.

Token and cost deltas include only identical cases with measurements available in both variants; coverage is reported explicitly. Demo usage is estimated and does not predict paid-model quality, billed cost, or production latency.
Paired token coverage: 28/30 cases.

## Observed failed cases

| Variant | Case | Failed checks |
| --- | --- | --- |
| baseline | `missing-sensor-001` | forbidden_sources_absent, uncertainty_disclosed |
| baseline | `missing-sensor-002` | uncertainty_disclosed |
| baseline | `missing-sensor-003` | uncertainty_disclosed, forbidden_sources_absent |
| baseline | `tool-failure-001` | required_tools_called, controlled_error_returned, uncertainty_disclosed |
| baseline | `tool-failure-002` | controlled_error_returned |
| baseline | `tool-failure-003` | controlled_error_returned, uncertainty_disclosed |
| baseline | `alarm-code-001` | alarm_mismatch_disclosed, required_sources_referenced |
| baseline | `alarm-code-002` | required_sources_referenced |
| baseline | `conflict-001` | contradiction_disclosed, required_sources_referenced |
| baseline | `conflict-002` | contradiction_disclosed, uncertainty_disclosed |
| baseline | `conflict-003` | contradiction_disclosed, required_sources_referenced |
| baseline | `tenant-002` | required_tools_called |
| baseline | `approval-003` | terminal_status_equals, exact_proposal_displayed |
| baseline | `long-context-002` | terminal_status_equals, required_tools_called, required_sources_referenced |
| baseline | `long-context-003` | terminal_status_equals, required_tools_called, required_sources_referenced, uncertainty_disclosed |
| optimized | `missing-sensor-001` | forbidden_sources_absent, uncertainty_disclosed |
| optimized | `missing-sensor-002` | uncertainty_disclosed |
| optimized | `missing-sensor-003` | uncertainty_disclosed, forbidden_sources_absent |
| optimized | `tool-failure-001` | required_tools_called, controlled_error_returned, uncertainty_disclosed |
| optimized | `tool-failure-002` | controlled_error_returned |
| optimized | `tool-failure-003` | controlled_error_returned, uncertainty_disclosed |
| optimized | `alarm-code-001` | alarm_mismatch_disclosed, required_sources_referenced |
| optimized | `alarm-code-002` | required_sources_referenced |
| optimized | `conflict-001` | contradiction_disclosed, required_sources_referenced |
| optimized | `conflict-002` | contradiction_disclosed, uncertainty_disclosed |
| optimized | `conflict-003` | contradiction_disclosed, required_sources_referenced |
| optimized | `tenant-002` | required_tools_called |
| optimized | `approval-003` | terminal_status_equals, exact_proposal_displayed |
| optimized | `long-context-001` | required_sources_referenced |
| optimized | `long-context-002` | terminal_status_equals, required_tools_called, required_sources_referenced |
| optimized | `long-context-003` | uncertainty_disclosed |

## What the optimized mode changes

- Applies the application's history message and character limits.
- Keeps the demo model fixed, so paid-model routing is not evaluated.
- Uses the same tenant-scoped retrieval and tool implementation as baseline.

## Limitations

- DemoProvider behavior differs from a probabilistic or paid model.
- Dataset tool-failure fixtures are not injected into the real registry, so those expectations may fail.
- Generated histories above 100 items are deterministically downsampled to the API limit while preserving declared relevant items.
- Prompt-injection resistance is not scored when the trace cannot prove the adversarial chunk was actually retrieved.
- Context-budget checks are not scored because provider request item counts are not persisted in telemetry.
- Result previews are capped by application telemetry, which limits full-content inspection.
