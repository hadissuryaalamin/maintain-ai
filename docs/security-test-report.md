# Security test report

Report date: 2026-07-21
Scope: synthetic local data, offline deterministic provider, FastAPI, tool registry,
approval service, telemetry, retrieval, and MCP adapter.

## Result

```text
python -m pytest -m "not live" -q
104 passed, 1 deselected, 1 upstream deprecation warning
```

The deselected test is the explicitly marked paid/live-provider smoke test. The result is a
repository test result, not a penetration test, production certification, or validation for
controlling physical equipment.

| Security property | Automated evidence | Result |
| --- | --- | --- |
| Query-level tenant isolation | Repository, retrieval, API manipulation, prompt exfiltration, analytics/run, approval, and MCP tests | Pass |
| Foreign alias confidentiality | Model/description aliases resolve only inside the internal trusted tenant context; explicit foreign IDs fail at the audited tool boundary | Pass |
| Prompt-injection containment | Hostile manual/incident fixtures remain delimited data and cannot grant tools, change tenant scope, or create a work order | Pass |
| Provider-output grounding | Application rebuilds factual fields from revalidated typed tool results; fabricated foreign IDs, values, summaries, causes, and actions are discarded | Pass |
| Tool authorization | Strict typed schemas exclude authority fields; unknown tools and model-supplied tenant/user/approval fields are rejected and audited | Pass |
| Human approval | No work order is created at proposal time; role, tenant, owner/manager, exact proposal, and explicit decision are checked | Pass |
| Idempotency and concurrency | Replays return one work order, conflicting key reuse is rejected, and concurrent confirmation has one database winner | Pass |
| Operational safety | Canonical lockout/tagout is first; live electrical work, safety defeat, and machinery-control actions are removed; invasive steps require shutdown | Pass |
| Privacy defaults | Prompts, free-text tool arguments, and tool bodies are not persisted by default | Pass |
| Resource bounds | Raw request, provider input, step, call, output-token, timeout, retry, and duplicate-call controls are exercised without a live network | Pass |
| Production fail-closed guard | Production mode rejects demo headers, automatic seed data, SQLite, and the fixed-identity MCP adapter | Pass |

Primary regression files are `tests/test_agent.py`, `tests/test_api_approval.py`,
`tests/test_tenant_retrieval.py`, `tests/test_tools.py`, `tests/test_mcp.py`, and
`tests/test_config.py`. The versioned scenario evaluation separately measures three
cross-tenant and three prompt-injection cases per optimization mode; see
`evals/reports/sample-scenario-comparison-v1.md`.

## Residual risk and production requirements

- Demo identity headers are intentionally not authentication. Production needs a verified
  OIDC/JWT adapter that derives tenant and user claims server-side.
- SQLite is a local demonstration database. Production needs PostgreSQL migration testing,
  row-level or equivalent defense in depth, rate limits, backups, and multi-process load tests.
- The deterministic provider and synthetic scenario fixtures cannot establish hosted-model
  quality, real equipment safety, or prompt-injection resistance against all inputs.
- Application-authored evidence statements protect the final structured response, but source
  records may still be wrong or stale. A qualified person must verify equipment state and use
  approved site/OEM procedures.
- Secrets, transport security, dependency scanning, infrastructure hardening, and external
  penetration testing remain deployment-owner responsibilities.

Report security issues through the private process in `SECURITY.md`; do not place sensitive
industrial data or credentials in a public issue.
