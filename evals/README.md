# Evaluation assets

This directory contains versioned, synthetic evaluation assets for the Industrial AI
Maintenance Operations Copilot. It does **not** contain measurements from a live
model, production equipment, or real maintenance records.

## Contents

- `cases/v1.json` - 30 synthetic cases, with three cases in every category required
  by `PROJECT_PLAN.md`.
- `schemas/evaluation-dataset-v1.schema.json` - JSON Schema for the dataset.
- `specs/rubric-v1.json` - deterministic metric definitions and scoring rules.
- `runner.py` - scenario/demo in-process integration runners plus a fixture-only replay.
- `scenario.py` - the test-only registry adapter and provider-request recorder used by the
  scenario backend.
- `reports/sample-scenario-comparison-v1.json` - raw 30-by-2 application results with
  declared synthetic tool outcomes, checks, telemetry, security events, and routing analysis.
- `reports/sample-scenario-comparison-v1.md` - concise scenario results and limitations.
- `reports/sample-demo-comparison-v1.json` - raw responses, database traces, checks,
  usage, cost, and latency from the actual demo application backend.
- `reports/sample-demo-comparison-v1.md` - concise summary of that demo integration run.
- `reports/sample-fixture-comparison-v1.json` - a paired baseline/optimized example
  made from declared fixture traces.
- `reports/sample-fixture-comparison-v1.md` - human-readable explanation of that
  example and its limitations.

## Run the scenario integration evaluation (recommended offline quality check)

```powershell
python -m evals.runner --dataset evals/cases/v1.json --mode both --backend scenario
```

This runs all 30 cases through FastAPI, the bounded agent loop, `DemoProvider`, telemetry,
tenant checks, and approval handling in both modes. Matching declared tool outcomes and
untrusted documents are injected only after normal tool-argument validation. Unexpected
tool calls continue to use the production synthetic-data tools and remain visible to the
scorer. The provider chooses tools from the request; the evaluator never copies required
tool lists into its policy, and measured failures remain failures.

The report also captures provider-request summaries for context-budget checks. Its separate
OpenAI routing-policy section runs the real `ModelRouter` without making provider calls and
prices the demo-estimated tokens as a clearly labeled shadow calculation. It does not claim
paid-model quality equivalence, billed cost, or realized savings.

## Run the demo integration evaluation (default)

From the repository root, run:

```powershell
python -m evals.runner --dataset evals/cases/v1.json --mode both
```

This runs every case once in baseline mode and once in optimized mode. Each run gets a
fresh temporary SQLite database, the real synthetic seed corpus, FastAPI `TestClient`,
and the deterministic `DemoProvider`. It overwrites
`evals/reports/sample-demo-comparison-v1.json` and its Markdown sibling.

The report captures the HTTP response, persisted agent run, model-usage events, tool
events, approvals, security events, work orders, measured in-process latency, and every
deterministic check result. It records real failures rather than substituting expected
fixture outcomes. Checks that cannot be supported by the current trace are marked
`not_evaluated` and excluded from their metric denominator with coverage reported.

The demo provider estimates tokens from characters and has a configured price of zero.
It does not exercise paid-model routing or support paid-provider savings claims. To run
a quick integration subset while developing, add `--limit 3`.

## Run the fixture-only contract replay

```powershell
python -m evals.runner --dataset evals/cases/v1.json --mode both --backend fixture
```

This overwrites `reports/sample-fixture-comparison-v1.*`. It validates cross-file
contract invariants, constructs expected safe traces, applies the declared checks, and
uses a documented deterministic token/cost estimator. It does **not** invoke FastAPI,
application tools, or a model. Its 100% conformance score is only a harness/dataset
self-check and must never be presented as application quality.

## Dataset contract

Every case declares:

1. authenticated tenant context (the only authoritative source of `tenant_id`),
2. the user message and optional generated-context recipe,
3. deterministic tool and retrieval fixture behavior,
4. required, optional, and forbidden tool calls,
5. the expected terminal status, and
6. named checks from `specs/rubric-v1.json` with case-specific parameters.

Fixture results are intentionally small. A fault-injection runner may inject them
through mocked tool/provider boundaries; they are not a second application data store. `tenant_id`
must be supplied from `tenant_context`, never copied from the user message or model
arguments.

For `generated_context`, construct entries in ascending numeric order using the
provided template and counts. Insert the declared `relevant_items` at their exact
positions. This makes long-context cases repeatable without committing megabytes of
padding text. The demo integration profile cannot send more than the API limit of 100
history messages, so it deterministically downsamples while retaining declared relevant
items and records the adaptation in each raw case result.

## Deterministic evaluation flow

1. Validate `cases/v1.json` against its schema.
2. Run every case through a clearly named demo, fixture, recorded, or live profile.
3. Capture the final structured response, tool-call trace, usage, latency, and cost.
4. Apply every case's `checks` exactly as defined in `rubric-v1.json`.
5. Aggregate the metric numerators and denominators; do not score non-applicable
   security checks as passes.
6. Preserve the raw run records alongside aggregates so results can be audited.

The schema can be validated with any JSON Schema Draft 2020-12 implementation. A
basic syntax-only check in PowerShell is:

```powershell
Get-Content -Raw evals/cases/v1.json | ConvertFrom-Json | Out-Null
Get-Content -Raw evals/specs/rubric-v1.json | ConvertFrom-Json | Out-Null
Get-Content -Raw evals/reports/sample-scenario-comparison-v1.json | ConvertFrom-Json | Out-Null
Get-Content -Raw evals/reports/sample-demo-comparison-v1.json | ConvertFrom-Json | Out-Null
Get-Content -Raw evals/reports/sample-fixture-comparison-v1.json | ConvertFrom-Json | Out-Null
```

## Reporting rules

- Label synthetic, replayed, mocked, and live runs distinctly.
- Never present `reports/sample-scenario-comparison-v1.*` as live-model performance; its
  tool outcomes are injected fixtures and its provider is deterministic.
- Never present `reports/sample-demo-comparison-v1.*` as paid- or live-model performance.
- Never present `reports/sample-fixture-comparison-v1.*` as application performance.
- A cost-saving claim must show the paired quality metrics and the pricing version.
- If provider usage is unavailable, record `null` plus `usage_quality: "unavailable"`,
  or label a declared estimator as `deterministic_estimate`; never represent an estimate
  as provider-reported usage or silently coerce an unavailable value to zero.
- Unsupported-claim rate is undefined when a response contains no factual claims;
  exclude such a run from that metric's denominator.
