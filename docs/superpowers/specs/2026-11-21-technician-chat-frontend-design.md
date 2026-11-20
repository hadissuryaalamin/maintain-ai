# Technician Chat Frontend — Design

Date: 2026-11-21
Status: Approved 2026-11-21
UI language: English only (user decision; no i18n layer).

## Intent

Maintenance technicians on the shop floor should be able to talk to the copilot the way they
talk to a colleague: describe a symptom, get an evidence-grounded preliminary diagnosis, and
approve a draft work order, all from a phone, a tablet mounted near the machine, or a desktop.
The current Streamlit dashboard is an engineering/demo surface (connection settings, raw
trace, analytics tabs) and is not built for that use.

The visual direction is fixed by the Stitch designs in `.stitch/designs/`
(project `8808783883346299433`, design system "Maintain AI Shopfloor"):

| Breakpoint | Reference |
|---|---|
| Phone (< 768px) | `mobile.html` / `mobile.png` |
| Tablet portrait (768–1023px) | `tablet-portrait.html` / `.png` |
| Tablet landscape (1024–1279px) | `tablet-landscape.html` / `.png` |
| Desktop (≥ 1280px) | `desktop-a2.html` / `.png` |

`.stitch/` is gitignored; the builder copies tokens and markup patterns from it into `web/`,
the reference files themselves stay local.

## Goals

1. A chat-first web app in `web/` that reproduces the Stitch layouts responsively.
2. When a technician opens the app, they immediately see the selected machine's status,
   active alarm and latest sensor readings — before asking anything.
3. Each assistant turn renders the `DiagnoseResponse` faithfully: tool trace, incident
   summary, possible causes with confidence, observations as evidence with source references,
   numbered recommended actions (flagging `requires_shutdown` / `requires_approval`),
   missing information, safety notice, and a pending approval card when present.
4. Approve / reject of a pending work order through the existing approval endpoint.
5. Large touch targets (≥ 48px, primary actions 56px) for gloved use.

## Non-goals

- Replacing or deleting the Streamlit dashboard. It stays for run trace and analytics.
- Real authentication. The app uses the existing demo identity headers.
- Server-side conversation persistence.
- Photo upload / image diagnosis.
- Editing a proposed work order (the API supports approve/reject only).
- Streaming responses.

## Anti-goals (failure even if it "works")

- Any UI that implies the app can control equipment: no "Emergency stop", "Dispatch",
  "Connected to SCADA", "Live stream" labels, no control-like buttons.
- Showing invented data. Every value on screen comes from the API or is a static, honest
  label. Stitch placeholder content (tank T-101, "PDF p.42", "94% similar", P-2 priority,
  estimated duration, crew, temperature/motor-current readings for A2, numeric confidence
  "0.68") must not ship.
- Presenting retrieved manual/incident text as trusted instructions. Evidence is displayed as
  quoted, attributed data.
- Weakening tenant isolation: new endpoints must go through `MaintenanceRepository` with the
  same tenant filter and cross-tenant audit behaviour as the tools.

## Constraints (from the existing project)

- API: FastAPI, endpoints `POST /incidents/diagnose`, `POST /approvals/{id}/confirm`,
  `GET /runs/{id}`, `GET /analytics/*`. Identity via `X-Tenant-ID` / `X-User-ID` headers,
  gated by `ALLOW_DEMO_AUTH`.
- `DiagnoseRequest.conversation_history` is supplied by the client (max 100 messages); the
  server trims it per `HISTORY_MESSAGE_LIMIT`.
- `PossibleCause.confidence` is `low | medium | high`, not a number.
- Seed sensor data is synthetic: 8 readings per metric over ~35 minutes on 2026-07-20, two
  metrics per machine (A2: `vibration_rms`, `suction_pressure`). A "last 24h from now"
  window would be empty.
- Demo identities (seed `users.json`): `user-a-tech`, `user-a-manager` (company-a),
  `user-b-tech`, `user-b-manager` (company-b).
- CI runs ruff, ruff format, mypy, pytest, and a Docker build. No Node toolchain today.

## Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **React + Vite + TypeScript + Tailwind in `web/`, built to static files served by FastAPI** | Reusable components across 4 breakpoints, typed API client, Vitest; adds Node/pnpm to CI and Docker | **Chosen** by the user |
| Plain HTML + Tailwind + vanilla JS served by FastAPI | No Node; chat/approval/machine state managed by hand, hard to test | Rejected |
| HTMX + Jinja from FastAPI | Python only; UI mixed into API, awkward for carousel/bottom sheet/collapsible trace | Rejected |

For machine context the user chose to **add read-only endpoints** rather than leave the
telemetry areas empty until the first question.

## Design

### 1. Backend: read-only machine endpoints

Add to `app/api/routes.py`, all depending on `get_auth_context` and using
`MaintenanceRepository`:

- `GET /machines` → `list[MachineSummary]` for the caller's tenant.
  New repository method `list_machines()` (tenant-filtered, ordered by id).
- `GET /machines/{machine_id}` → `MachineSummary`. Uses existing `get_machine` (missing and
  cross-tenant both return 404 and are audited).
- `GET /machines/{machine_id}/sensors?limit=N` → `MachineSensors`: for each metric the machine
  has, the most recent `limit` readings (default 12, max 200) ordered by time, plus
  `latest` value, unit and quality. Window is anchored on the machine's latest reading, not
  on wall-clock now. New repository method, tenant-filtered.

`MachineSummary`: `id, name, model, line, status, condition, active_alarm, criticality,
hourly_downtime_cost, cost_currency, last_status_at`.

Sensor bands (normal/elevated/alarm) are **not** exposed by the API; the UI colours a reading
only from its `quality` and the machine's `condition`/`active_alarm`. No thresholds are
hard-coded in the frontend.

Tests (pytest, existing conftest fixtures): list scoped to tenant; cross-tenant `GET` returns
404 and writes a security event; sensors grouped by metric and limited; missing auth headers
→ 422/401 as today.

### 2. Frontend app (`web/`)

Stack: Vite, React 18, TypeScript (strict), Tailwind 3, pnpm. No UI kit; components are
hand-built from the Stitch markup. Material Symbols for icons, IBM Plex Sans + JetBrains Mono
self-hosted or via Google Fonts.

Design tokens: taken from `desktop-a2.html` Tailwind config (surface, surface-container-*,
primary `#F5A524`, status-critical/warning/normal, outline) into `tailwind.config.ts`.

Structure:

```
web/src/
  api/client.ts        typed fetch wrapper, adds identity headers, maps errors
  api/types.ts         hand-written types mirroring app/schemas (DiagnoseResponse etc.)
  state/               conversation store (React context + reducer)
  components/
    AppShell           responsive frame: sidebar / rail / drawer per breakpoint
    ConversationList   history grouped Today / Earlier
    MachineBar         machine pill, alarm chip, latest readings strip
    MachinePanel       right panel (desktop) / slide-over (tablet) / bottom sheet (phone)
    SensorSparkline    inline SVG from /sensors readings
    UserBubble
    AssistantTurn      composes the pieces below
    ToolTrace          collapsible list from tool_trace (name, status, latency_ms)
    DiagnosisCard      incident_summary, possible_causes, confidence bars
    EvidenceList       observations → cards (source_type icon, source_reference)
    ActionSteps        recommended_actions, badges for shutdown/approval
    SafetyBanner       safety_notice
    MissingInfo        missing_information list
    ApprovalCard       pending_approval → approve/reject
    Composer           quick chips, textarea, mic, send
    IdentityPicker     demo tenant/user switcher
```

Layout per breakpoint (matches Stitch):

```
desktop  [sidebar 280][   chat max 760-940   ][machine panel 340]
landscape[rail 72][        chat max 760        ]  panel = slide-over
portrait [ app bar + 3 sensor tiles            ]  list = drawer, panel = bottom sheet
phone    [ app bar + scrollable sensor strip   ]  evidence = swipe carousel
```

The mobile bottom tab bar from the Stitch mobile screen is dropped (its tabs have no backing
features).

### 3. Behaviour

- **Identity**: the picker sets `tenantId`/`userId` (default `company-a` / `user-a-tech`,
  overridable by `VITE_DEMO_TENANT_ID` / `VITE_DEMO_USER_ID`). Changing identity clears the
  in-memory machine list and selects that tenant's first machine.
- **Machine context**: on load and on machine change, fetch `/machines` and
  `/machines/{id}/sensors`. Composer machine chip changes the selected machine. The selected
  machine id is prefixed to the outgoing message only if the user's text doesn't already
  mention it (e.g. `"[Machine A2] grinding noise…"`) — the agent identifies machines from
  text today.
- **Sending**: `POST /incidents/diagnose` with the message and the conversation's prior
  turns as `conversation_history` (assistant turns serialised as their `incident_summary`).
  While pending: disabled send, "Checking machine data…" placeholder turn. Request timeout
  60s with a retry button.
- **Errors**: `status != completed` or `error` set → assistant turn shows the error text and
  `run_id`; HTTP 4xx/5xx → inline error with retry. No raw stack traces.
- **Confidence**: `low/medium/high` → 1/3/5 filled bars plus the word. No numeric score.
- **Approval**: approve/reject call `/approvals/{id}/confirm` with a client-generated
  `idempotency_key` (UUID, reused on retry). On approve, the card shows the returned
  `work_order_id` and status "Draft created"; on reject, "Rejected". Buttons disabled after
  a decision. Fixed footer text: "Creates a draft only. No equipment action is taken."
- **Quick chips**: insert prompt text into the composer (do not auto-send):
  "Show recent sensor readings", "Similar past incidents", "Relevant manual section",
  "Downtime cost if stopped".
- **"Draft work order" button** on an assistant turn: sends a follow-up asking the agent to
  propose a draft work order for the current machine; the approval card comes back through
  the normal flow.
- **Mic**: browser Web Speech API dictation into the textarea when available; button hidden
  when not supported. No audio leaves the browser except via the browser's own service.
- **Conversation history (sidebar)**: stored in `localStorage` keyed by tenant+user, max 20
  conversations; wrapped in try/catch, app works without it. "New conversation" starts empty.
- **Run link**: each assistant turn has a small "Run trace" link showing `run_id` (opens the
  Streamlit trace view URL if `VITE_DASHBOARD_URL` is set, otherwise copies the id).

### 4. Serving and tooling

- Dev: `pnpm dev` in `web/` with Vite proxy `/api/* → http://127.0.0.1:8000/api/*` (API routes
  already live under `/api/v1`).
- Prod: `pnpm build` → `web/dist`. FastAPI mounts it with `StaticFiles(html=True)` at `/app`
  when the directory exists (setting `WEB_DIST_PATH`, default `web/dist`); API stays at its
  current paths. Same origin, no CORS.
- Dockerfile: add a `node:22-slim` build stage running `pnpm install --frozen-lockfile &&
  pnpm build`, copy `dist` into the runtime image.
- CI: new `web` job — pnpm install, `pnpm lint` (eslint), `pnpm typecheck`, `pnpm test`
  (Vitest + Testing Library), `pnpm build`.
- `.gitignore`: add `web/node_modules/`, `web/dist/`.
- README: short "Technician chat app" section.

### 5. Testing

- Backend: pytest for the three endpoints (above).
- Frontend unit/component (Vitest + Testing Library, `fetch` mocked):
  DiagnoseResponse fixture renders cause, confidence, evidence, steps, safety, approval;
  error response renders error state; approve sends idempotency key and disables buttons;
  identity change refetches machines; no element contains the strings "SCADA", "Emergency",
  "Dispatch".
- Manual check at 390, 768, 1024, 1440px widths against the Stitch PNGs.

## Builder's calls (decided in this document, not by the user)

- Breakpoints and mapping to the four Stitch screens.
- Endpoint shapes and the "latest N readings" window.
- Mount path `/app`, pnpm, Vitest, eslint, no UI kit.
- localStorage for conversation list; Web Speech API for mic; camera button omitted.
- Dropping the Stitch bottom tab bar and the "Edit" work-order button.
- Assistant turns serialised as `incident_summary` in `conversation_history`.

## Left to the builder

- Exact component splitting and file names beyond the outline above.
- Copy for empty, loading and error states (short, plain, consistent with the safety tone).
- Whether fonts are self-hosted or loaded from Google Fonts.
