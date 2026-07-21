# Security model

The security objective is fail-closed maintenance assistance: evidence can inform
a diagnosis, but neither evidence nor model output can grant permission, select an
authoritative tenant, or directly control equipment.

## Trust boundaries

| Input | Trust treatment |
| --- | --- |
| User incident text | Untrusted; validated and bounded |
| Manuals and incident records | Untrusted data, never instructions |
| Sensor/tool results | Untrusted evidence, delimited before model use |
| Model tool arguments | Untrusted; schema and allowlist validated |
| Tenant/user context | Trusted only after application authentication |
| Approval confirmation | Trusted only after identity, proposal, and idempotency checks |

## Local identity and production authentication

The demo accepts `X-Tenant-ID` and `X-User-ID`. This makes tenant isolation easy to
demonstrate but allows any caller to choose an identity, so it must not be exposed
to an untrusted network.

Setting `APP_ENV=production` fails validation if demo-header authentication, automatic
synthetic seeding, or SQLite remains enabled. Because this repository intentionally does not
pretend to include a production identity adapter, a safely configured production-mode API
returns `503` until that adapter is supplied.

The dashboard takes its API origin from `API_BASE_URL` at process startup and locks
the field by default, avoiding a browser user turning the Streamlit server into an
arbitrary HTTP client. URL editing is an explicit local-only opt-in.

For production, place the API behind an OIDC/OAuth2 proxy or implement JWT
validation in the API. Derive the tenant and user from verified claims, ignore any
caller-supplied identity headers at the public edge, enforce issuer/audience and
expiry, and map users to tenant membership server-side. Use TLS for every hop.

## Tenant isolation

- The API creates a tenant context before invoking the agent or telemetry layer.
- `tenant_id` is not part of a model-visible tool schema. Tool execution injects
  it from context.
- Every machine, sensor, incident, document, work-order, approval, and run query
  includes a tenant predicate. Prompt wording is never the isolation control.
- Cross-tenant identifiers are answered as not found/forbidden without returning
  the other tenant's existence or data and are recorded as security events.
- Analytics and run-detail endpoints are tenant-scoped too; operational data can
  itself reveal sensitive activity.

Use a separate database role, schema, or PostgreSQL row-level security as an
additional production control. It complements but does not replace application
tests and query scoping.

## Prompt-injection controls

Retrieved content is wrapped as quoted evidence with provenance and a fixed rule
that it cannot change policy, request tools, or grant permissions. The agent may
summarise statements such as "ignore previous instructions" as document content,
but must not follow them. Tool names remain allowlisted, arguments are typed, and
state-changing tools pass through a separate approval service.

Do not add retrieved text to system/developer instruction positions. Do not
interpolate it into SQL, shell commands, URLs, or provider configuration. Limit
chunk size and result count to reduce both injection surface and cost.

## Final-output grounding

Successful tool results are revalidated and converted into application-authored observations.
The final response does not trust a provider-authored statement merely because it cites a real
reference: provider summaries, observations, cause reasoning, missing-information prose, and
recommended actions are replaced with evidence-bounded or status-specific text. Cause entries
remain explicitly unconfirmed and low confidence. The application inserts lockout/tagout first,
generates subsequent steps from evidence categories, marks invasive work as requiring shutdown,
and removes live-electrical, safety-defeat, and machinery-control suggestions.

## Approval and idempotency

`create_work_order` is the only intended state-changing model tool. The agent first
requires explicit work-order intent in the current user message; retrieved content
cannot authorize even a proposal. An allowed model request creates a pending proposal,
not a work order. The UI displays the exact machine, title, description, and priority.
A user then explicitly approves or rejects it.

On confirmation the API must verify all of the following:

1. The approval belongs to the caller's tenant.
2. The caller has an allowlisted work-order approver role (`technician` or `manager`) and is
   either the original proposer or a manager for that tenant.
3. The proposal is still pending and its stored arguments have not changed.
4. The submitted idempotency key has not been used for a different request.
5. The resulting work-order identifier is stored on the approval result.

Repeated delivery of the same confirmation returns the original result. It must
not create another work order.

## MCP boundary

The local MCP process receives its tenant from `MCP_TENANT_ID` at startup; MCP tool
arguments cannot override it. Run one instance per trusted tenant for this demo.
Do not use a caller-controlled environment or command-line value in a shared
service. Production multi-tenant MCP needs authenticated transport, authorization,
rate limiting, and construction of tenant context from verified claims.

Only read-only tools are exposed. Adding a write tool requires a protocol-aware
approval design with equivalent guarantees to the HTTP workflow; it must not call
the repository directly.

## Secrets and logs

- Keep provider keys in an environment secret manager. `.env` is ignored and
  `.env.example` contains placeholders only.
- Never put keys in browser state, incidents, tool results, Docker images, or Git.
- Log identifiers, event types, durations, counts, controlled error categories,
  and security outcomes. `STORE_PROMPT_PREVIEW=false` and `STORE_TOOL_PAYLOADS=false`
  are the defaults: free-text tool arguments and result bodies are redacted from traces.
  Approval proposals remain in the dedicated tenant-scoped approval record because the exact
  proposed state change must be reviewable. Do not log raw provider responses.
- Redact authorization headers and rotate a key immediately if it reaches logs or
  version control.

## Security verification checklist

- Cross-tenant machine, run, analytics, approval, and work-order requests fail
  closed.
- Direct payload attempts to set `tenant_id` are rejected or ignored.
- Injection text in manuals and incidents does not alter policy or cause writes.
- Unknown tools and invalid arguments return controlled errors.
- Work orders cannot be created without approval; duplicate confirms are
  idempotent.
- Errors never return credentials, raw stack traces, or another tenant's data.

The dated automated evidence and residual-risk statement are in the
[security test report](security-test-report.md).
