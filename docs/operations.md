# Operations runbook

## Service checks

| Component | Check | Healthy result |
| --- | --- | --- |
| API | `GET /health` | HTTP 200 and ready status |
| Dashboard | `GET /_stcore/health` | HTTP 200 |
| MCP | Connect and list tools | `get_machine_status` is advertised |
| Database | Submit/read a synthetic run | Same tenant can retrieve it |
| Provider | Controlled smoke diagnosis | Success with usage or explicit unavailable fields |

For the local stack:

```bash
docker compose ps
docker compose logs --tail 100 api
docker compose logs --tail 100 dashboard
docker compose logs --tail 100 mcp
```

Logs should contain identifiers and controlled categories, not full prompt or tool
content. Treat copied production logs as sensitive.

Persisted run telemetry follows the same default: prompt previews and free-text tool payloads
are redacted unless an operator explicitly enables `STORE_PROMPT_PREVIEW` or
`STORE_TOOL_PAYLOADS`. Enabling either increases the data-retention and access-control burden.

## Operational indicators

Monitor at least:

- request count, error rate, and p50/p95/p99 latency by endpoint;
- model latency, retry rate, timeout rate, and provider error category;
- input/output/cached tokens and estimated cost by tenant, model, and task type;
- agent steps, tool-call count, validation failures, and tool failure rate;
- task success, grounded-answer, unsupported-claim, tenant-isolation, and
  prompt-injection evaluation rates;
- pending approval age, approval outcomes, and idempotent replay count;
- database size, connection pressure, write latency, and backup age.

Alert on sustained API errors or latency, cost velocity outside an expected band,
provider authentication failures, repeated limit exhaustion, cross-tenant attempts,
or any failed security evaluation. Cost is estimated when provider usage or pricing
is incomplete; never silently interpret missing usage as zero.

## Common incidents

### API is unhealthy

1. Inspect `docker compose ps` and API logs.
2. Confirm the database volume is writable and configuration paths exist.
3. Check that the configured provider name/model is valid. A provider outage should
   return a controlled application error rather than fail process startup where
   the demo/local path remains available.
4. Restart only the affected process after capturing diagnostic context.

### Provider timeouts or rate limits

1. Confirm the error category and provider status without logging request content.
2. Verify bounded retries and exponential backoff are working; do not increase
   retries until they exceed agent or request limits.
3. Route eligible simple traffic to the configured smaller model or temporarily
   reduce concurrency.
4. Tell users a run failed or timed out; do not claim tool inspection occurred.

### Cost spike

1. Break down cost by tenant, model, task type, run, and agent step.
2. Look for repeated equivalent tool calls, unusually long retrieved chunks, long
   conversation history, or provider retries.
3. Apply rate/budget controls before changing quality-sensitive routing.
4. Re-run the evaluation suite before claiming a remediation saves cost safely.

### Cross-tenant alert

1. Preserve security logs and the request/run identifiers.
2. Disable the affected credential/session or isolate the service if data exposure
   is suspected.
3. Verify API, repository, telemetry, approval, and MCP scopes independently.
4. Determine whether any data was returned; notify according to the organisation's
   incident-response and legal process.
5. Add a deterministic regression case before restoring service.

### Approval appears stuck

1. Load the run using the same tenant/user context and inspect proposal status.
2. Check confirmation logs by approval ID and idempotency key hash/identifier.
3. Retry with the same idempotency key if the first response was lost.
4. Never create a work order manually just to make UI state agree. Reconcile the
   approval and work-order records transactionally.

## Backup and restore

For the local SQLite demo, stop writers before copying the database from the named
volume. A raw copy taken during writes may be inconsistent. To reset synthetic
demo data intentionally, stop the stack, remove its named volume, and start it
again so normal initialisation runs.

Production PostgreSQL should use encrypted automated backups and point-in-time
recovery. Test restores into an isolated environment on a schedule, including
record counts and tenant-scoped smoke queries. Backups contain maintenance data and
telemetry and must follow the same access and retention rules as the primary data.

## Data and model changes

- Version prompts, model routing, prices, retrieval settings, and evaluation data.
- Record the price version and effective date used for each cost estimate.
- Run deterministic security gates and quality/cost evaluations before promotion.
- Keep a rollback path for application, configuration, prompt, and schema changes.
- Do not compare baseline and optimised runs across different case or pricing
  versions without labeling the mismatch.
