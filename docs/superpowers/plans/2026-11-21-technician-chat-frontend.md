# Technician Chat Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a responsive, chat-first technician web app (`web/`) backed by three new read-only machine endpoints, served by FastAPI at `/app`.

**Architecture:** FastAPI gains `GET /api/v1/machines`, `/machines/{id}`, `/machines/{id}/sensors` built on `MaintenanceRepository` (tenant-filtered, audited). A Vite + React + TypeScript + Tailwind SPA calls these plus the existing diagnose/approval endpoints with demo identity headers; production build is mounted by FastAPI with `StaticFiles` so everything is same-origin.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest · Node 22, pnpm 9, Vite 5, React 18, TypeScript 5 (strict), Tailwind 3, Vitest 2 + @testing-library/react, eslint 9.

**Spec:** `docs/superpowers/specs/2026-11-21-technician-chat-frontend-design.md`
**Visual reference (local, gitignored):** `.stitch/designs/{mobile,tablet-portrait,tablet-landscape,desktop-a2}.{html,png}`

## Global Constraints

- UI copy is English only; no i18n layer.
- All API routes live under `/api/v1` (existing `APIRouter(prefix="/api/v1")`).
- Identity headers: `X-Tenant-ID`, `X-User-ID`. Defaults `company-a` / `user-a-tech`; env `VITE_DEMO_TENANT_ID`, `VITE_DEMO_USER_ID`.
- Demo identities: `user-a-tech`, `user-a-manager` (company-a); `user-b-tech`, `user-b-manager` (company-b).
- Touch targets ≥ 48px; primary actions (send, mic, approve, recommended-check rows) 56px.
- Tokens (from `desktop-a2.html`): `primary #F5A524`, `on-primary #000000`, `primary-container #3D2800`, `on-primary-container #FFDFA6`, `surface #0E1116`, `surface-container-low #141820`, `surface-container #1A202C`, `surface-container-high #222B3A`, `on-surface #F0F3F8`, `on-surface-variant #9DA8B9`, `outline #323E50`, `status-critical #EF4444`, `status-warning #F5A524`, `status-normal #22C55E`. Fonts: IBM Plex Sans (body/headline), JetBrains Mono (IDs, values, timestamps).
- Breakpoints: phone < 768, tablet portrait 768–1023, tablet landscape 1024–1279, desktop ≥ 1280 (Tailwind `md`=768, `lg`=1024, `xl`=1280).
- Forbidden UI strings anywhere in rendered output: `SCADA`, `Emergency`, `Dispatch`, `Live stream`. No numeric confidence; no invented values (no thresholds, durations, crews, part numbers).
- Approval footer copy, exact: `Creates a draft only. No equipment action is taken.`
- Composer disclaimer, exact: `AI suggestions are preliminary. Verify with the OEM manual and site procedures.`
- Assistant header status, exact: `Read-only access · cannot control equipment`
- Message length: 3–10000 chars (API `DiagnoseRequest.message`).
- Sensors `limit`: default 12, min 1, max 200.
- Conversation list in `localStorage`, key `maintain-ai:conversations:{tenantId}:{userId}`, max 20 conversations; every access in try/catch.

## Review Focus

1. Identity or machine switched while a diagnose request is in flight → the late response must not be appended to the new conversation. (Test in Task 5.)
2. Diagnose returns `status` other than `completed` with `diagnostic: null` (and maybe `pending_approval: null`) → turn shows error text and run id, no crash. (Test in Task 6.)
3. Double-tap / retry on Approve → same `idempotency_key` sent, buttons disabled after first tap. (Test in Task 7.)
4. Sensor readings with `value: null` or `quality` ≠ `good` → shown as `—` with quality label, sparkline skips the point. (Tests in Tasks 1 and 4.)
5. `localStorage` throws (private mode) → app still loads and chats; list just isn't remembered. (Test in Task 5.)

---

## File Structure

```
app/schemas/api.py                 + MachineSummary, SensorSeries, SensorPointOut, MachineSensors
app/db/repositories.py             + list_machines(), latest_sensor_readings()
app/api/routes.py                  + 3 GET routes
app/config.py                      + web_dist_path: Path = Path("web/dist")
app/main.py                        mount StaticFiles at /app when dir exists
tests/test_api_machines.py         new
tests/test_web_mount.py            new
web/                               new Vite app (package.json, vite.config.ts, tailwind.config.ts, eslint.config.js, index.html, src/**)
  src/api/types.ts                 TS mirrors of API schemas
  src/api/client.ts                ApiClient
  src/state/identity.tsx           IdentityProvider + useIdentity
  src/state/conversations.ts       reducer + storage helpers
  src/state/ConversationProvider.tsx
  src/hooks/useMachines.ts
  src/components/*.tsx             per spec §2 list
  src/test/fixtures.ts             DiagnoseResponse / machine fixtures
Dockerfile                         node build stage
.github/workflows/ci.yml           + web job
.gitignore                         + web/node_modules/, web/dist/
README.md                          + "Technician chat app" section
```

---

### Task 1: Read-only machine endpoints

**Files:**
- Modify: `app/schemas/api.py`, `app/db/repositories.py`, `app/api/routes.py`
- Test: `tests/test_api_machines.py`

**Interfaces:**
- Produces (HTTP, consumed by Task 3 types):
  - `GET /api/v1/machines` → `MachineSummary[]`
  - `GET /api/v1/machines/{machine_id}` → `MachineSummary` | 404 `{"detail":"Machine not found."}`
  - `GET /api/v1/machines/{machine_id}/sensors?limit=12` → `MachineSensors` | 404
- Schemas (pydantic, `ApiSchema` base):
  - `MachineSummary`: `id: str, name: str, model: str, line: str, status: str, condition: str | None, active_alarm: str | None, criticality: str | None, hourly_downtime_cost: Decimal, cost_currency: str | None, last_status_at: datetime | None`
  - `SensorPointOut`: `value: float | None, quality: str, recorded_at: datetime`
  - `SensorSeries`: `metric: str, unit: str, latest: SensorPointOut | None, readings: list[SensorPointOut]`
  - `MachineSensors`: `machine_id: str, series: list[SensorSeries]`
- Repository:
  - `MaintenanceRepository.list_machines(self) -> list[Machine]` — tenant-filtered, ordered by `Machine.id`.
  - `MaintenanceRepository.latest_sensor_readings(self, *, machine_id: str, limit: int) -> dict[str, list[SensorReading]]` — calls `get_machine` first (reuses audit/404 path); per metric, the last `limit` readings ordered ascending by `recorded_at`; keys sorted by metric name.
- `condition`, `criticality`, `cost_currency`, `last_status_at` come from `Machine.metadata_json` (seed stores them there; `last_status_at` parsed with `datetime.fromisoformat`). `active_alarm` = `Machine.alarm_code`.

- [ ] **Step 1: Write failing tests** in `tests/test_api_machines.py` using `api_client`, `headers_a`, `headers_b`:
  - `test_list_machines_is_tenant_scoped`: company-a → ids `["A1","A2"]`; company-b → `["B1","B2"]`.
  - `test_machine_summary_fields`: `GET /machines/A2` → `condition == "warning"`, `active_alarm == "VIB-HI"`, `criticality == "medium"`, `hourly_downtime_cost == "1800.00"` (string or numeric equality with Decimal 1800), `cost_currency == "USD"`.
  - `test_cross_tenant_machine_is_404_and_audited`: headers_b `GET /machines/A2` → 404; `SecurityEvent` count with `event_type == "cross_tenant_access_denied"` and `target_id == "A2"` increases by 1.
  - `test_sensors_grouped_and_limited`: `GET /machines/A2/sensors?limit=3` → metrics `["suction_pressure","vibration_rms"]`, each `len(readings) == 3`, readings ascending, `latest == readings[-1]`.
  - `test_sensors_limit_bounds`: `limit=0` and `limit=201` → 422.
  - `test_sensors_cross_tenant_404`: headers_b on `/machines/A2/sensors` → 404.
  - `test_sensor_null_value_passes_through`: insert a `SensorReading(value=None, quality="missing")` for A2 `vibration_rms` with the newest timestamp via `database.session()`; response `latest.value is None`, `latest.quality == "missing"`.
  - `test_machines_require_identity_headers`: no headers → 422.
- [ ] **Step 2: Run** `pytest tests/test_api_machines.py -q` → all FAIL (404 route not found).
- [ ] **Step 3: Implement** schemas, repository methods, routes. Routes catch `TenantAccessDenied` → `session.commit()` (persist audit) then `HTTPException(404, "Machine not found.")`, mirroring `get_run`. `limit: Annotated[int, Query(ge=1, le=200)] = 12`.
- [ ] **Step 4: Run** `pytest tests/test_api_machines.py -q` → PASS; `pytest -m "not live" -q` → PASS; `ruff check . && ruff format --check . && mypy app` → clean.
- [ ] **Step 5: Commit** `feat(api): add read-only machine and sensor endpoints`

### Task 2: Serve built web app at /app

**Files:**
- Modify: `app/config.py`, `app/main.py`, `.gitignore`
- Test: `tests/test_web_mount.py`

**Interfaces:**
- Produces: `Settings.web_dist_path: Path = Path("web/dist")` (env `WEB_DIST_PATH`). When `web_dist_path / "index.html"` exists at `create_app` time, `application.mount("/app", StaticFiles(directory=..., html=True), name="web")`. Otherwise no mount (API-only runs unaffected).

- [ ] **Step 1: Write failing tests**:
  - `test_web_mounted_when_dist_exists(tmp_path, settings, database)`: write `tmp_path/"dist"/"index.html"` with `<div id="root"></div>`; `create_app(settings=settings.model_copy(update={"web_dist_path": tmp_path/"dist"}), database=database, provider=DemoProvider())`; `GET /app/` → 200, body contains `id="root"`.
  - `test_web_not_mounted_when_missing`: `web_dist_path=tmp_path/"nope"` → `GET /app/` → 404; `GET /health` → 200.
- [ ] **Step 2: Run** `pytest tests/test_web_mount.py -q` → FAIL.
- [ ] **Step 3: Implement** setting + conditional mount after `include_router`. Add `web/node_modules/` and `web/dist/` to `.gitignore`.
- [ ] **Step 4: Run** `pytest -m "not live" -q`, ruff, mypy → clean.
- [ ] **Step 5: Commit** `feat(api): serve technician web app at /app when built`

### Task 3: Scaffold `web/` with tokens, types and API client

**Files:**
- Create: `web/package.json`, `web/pnpm-lock.yaml`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tailwind.config.ts`, `web/postcss.config.js`, `web/eslint.config.js`, `web/index.html`, `web/src/main.tsx`, `web/src/index.css`, `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/test/setup.ts`, `web/src/test/fixtures.ts`
- Test: `web/src/api/client.test.ts`

**Interfaces:**
- Scripts: `dev`, `build` (`tsc -b && vite build`), `typecheck` (`tsc -b --noEmit`), `lint` (`eslint .`), `test` (`vitest run`).
- Vite: `base: "/app/"`; dev proxy `"/api" → "http://127.0.0.1:8000"`.
- `types.ts` mirrors exactly: `MachineSummary`, `SensorPointOut`, `SensorSeries`, `MachineSensors` (Task 1); `DiagnoseRequest`, `ConversationMessage`, `DiagnoseResponse`, `ToolTraceItem`, `UsageSummary`, `PendingApproval`, `ApprovalDecisionRequest`, `ApprovalDecisionResponse` (`app/schemas/api.py`); `DiagnosticResult`, `Observation`, `PossibleCause`, `RecommendedAction`, `Confidence = "low"|"medium"|"high"`, `SourceType = "tool"|"manual"|"incident_history"|"user"` (`app/schemas/diagnostic.py`). Decimal fields typed `string | number`.
- `client.ts`:
  - `class ApiError extends Error { status: number | null }`
  - `createApiClient(identity: { tenantId: string; userId: string }, opts?: { baseUrl?: string; timeoutMs?: number }) => ApiClient` (baseUrl default `"/api/v1"`, timeout default 60000)
  - `ApiClient`: `listMachines(signal?) : Promise<MachineSummary[]>`, `getMachineSensors(id: string, limit?: number, signal?) : Promise<MachineSensors>`, `diagnose(req: DiagnoseRequest, signal?) : Promise<DiagnoseResponse>`, `decideApproval(id: string, req: ApprovalDecisionRequest, signal?) : Promise<ApprovalDecisionResponse>`.
  - Error message: `detail` string from JSON body if present, else `"Request failed (HTTP {status})."`; network/timeout → `"Could not reach the server."` with `status: null`.
- `fixtures.ts` exports `machineA2: MachineSummary`, `sensorsA2: MachineSensors`, `diagnoseCompleted: DiagnoseResponse` (2 causes, 3 observations of types manual/incident_history/tool, 3 actions one with `requires_shutdown: true`, 1 missing_information item, pending_approval with `proposed_action: { machine_id:"A2", title:"Inspect pump inlet", description:"…", priority:"high" }`), `diagnoseFailed: DiagnoseResponse` (`status:"failed"`, `diagnostic:null`, `error:"Model request failed safely."`).

- [ ] **Step 1: Scaffold** with `pnpm create vite web --template react-ts`, add deps (tailwind, postcss, autoprefixer, vitest, jsdom, @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, eslint, typescript-eslint, eslint-plugin-react-hooks). Tailwind theme extended with the Global Constraints tokens, `fontFamily.body/headline = ["IBM Plex Sans", …]`, `mono = ["JetBrains Mono", …]`. Fonts + Material Symbols via Google Fonts links in `index.html`. Body `bg-surface text-on-surface font-body`.
- [ ] **Step 2: Write failing tests** `client.test.ts` (mock `fetch`):
  - `sends identity headers` — every call has `X-Tenant-ID`/`X-User-ID`.
  - `diagnose posts JSON to /api/v1/incidents/diagnose`.
  - `getMachineSensors passes limit query`.
  - `maps 404 detail to ApiError` — message `"Machine not found."`, status 404.
  - `maps network failure` — message `"Could not reach the server."`, status null.
- [ ] **Step 3: Run** `pnpm -C web test` → FAIL.
- [ ] **Step 4: Implement** `types.ts`, `client.ts`, fixtures.
- [ ] **Step 5: Run** `pnpm -C web lint && pnpm -C web typecheck && pnpm -C web test && pnpm -C web build` → all pass.
- [ ] **Step 6: Commit** `feat(web): scaffold technician app with typed API client`

### Task 4: Identity, machine context and telemetry UI

**Files:**
- Create: `web/src/state/identity.tsx`, `web/src/hooks/useMachines.ts`, `web/src/components/{AppShell,IdentityPicker,MachineBar,MachinePanel,SensorSparkline,MachineSelector}.tsx`, `web/src/App.tsx`
- Test: `web/src/hooks/useMachines.test.tsx`, `web/src/components/MachineBar.test.tsx`, `web/src/components/SensorSparkline.test.tsx`

**Interfaces:**
- Consumes: `createApiClient`, types (Task 3).
- Produces:
  - `IdentityProvider`, `useIdentity(): { tenantId; userId; setIdentity(t: string, u: string): void; client: ApiClient }`. `DEMO_IDENTITIES` constant: the four seed users with display names `Avery Technician`, `Alex Manager`, `Bailey Technician`, `Blair Manager`.
  - `useMachines(): { machines: MachineSummary[]; selected: MachineSummary | null; select(id: string): void; sensors: MachineSensors | null; loading: boolean; error: string | null; reload(): void }` — on identity change: abort in-flight, clear, fetch list, select first; on select: fetch sensors (limit 12).
  - `formatMetric(metric: string): string` in `MachineBar.tsx` — `vibration_rms` → `Vibration RMS`, `suction_pressure` → `Suction pressure` (snake_case → sentence case, `rms` uppercased).
  - `AppShell` props: `{ sidebar: ReactNode; header: ReactNode; panel: ReactNode; children: ReactNode }`. Layout: `xl` sidebar 280 + panel 340 inline; `lg` 72px icon rail + panel as right slide-over; `md` app bar + drawer + panel bottom sheet; base same as `md` with sensor strip horizontally scrollable.
- Status colouring: machine `condition`/`status` → `warning` amber, `stopped`/`critical` red, otherwise green; reading with `quality !== "good"` or `value === null` → shows `—` and quality text in `on-surface-variant`.

- [ ] **Step 1: Write failing tests**:
  - `useMachines selects first machine and loads its sensors` (mock client: list `[A1,A2]`) → `selected.id === "A1"`, `getMachineSensors` called with `"A1", 12`.
  - `useMachines refetches on identity change and drops stale results` — switch identity before first list resolves; final `machines` are company-b's.
  - `MachineBar shows name, alarm and latest readings` — renders `A2`, `Process Cooling Pump`, `VIB-HI`, `Vibration RMS`, value with unit.
  - `MachineBar shows dash for missing reading` — latest `{value:null, quality:"missing"}` → `—` and `missing`.
  - `SensorSparkline skips null points` — polyline `points` attribute has `readings.filter(v => v.value !== null).length` pairs.
- [ ] **Step 2: Run** `pnpm -C web test` → FAIL.
- [ ] **Step 3: Implement** components using markup/classes adapted from the Stitch HTML for each breakpoint.
- [ ] **Step 4: Run** lint, typecheck, test → pass. `pnpm -C web dev` with API running: page shows A1 by default, switching to A2 shows VIB-HI and two metrics.
- [ ] **Step 5: Commit** `feat(web): machine context, identity picker and telemetry`

### Task 5: Conversations, composer and send flow

**Files:**
- Create: `web/src/state/conversations.ts`, `web/src/state/ConversationProvider.tsx`, `web/src/components/{ConversationList,Composer,UserBubble,Thread}.tsx`
- Test: `web/src/state/conversations.test.ts`, `web/src/components/Composer.test.tsx`, `web/src/state/ConversationProvider.test.tsx`

**Interfaces:**
- Consumes: `useIdentity`, `useMachines`, `ApiClient.diagnose` (Tasks 3–4).
- Produces:
  - Types: `Turn = { id: string; role: "user"; text: string; at: string } | { id: string; role: "assistant"; at: string; state: "pending" } | { id: string; role: "assistant"; at: string; state: "done"; response: DiagnoseResponse } | { id: string; role: "assistant"; at: string; state: "error"; message: string; retryText: string }`; `Conversation = { id: string; title: string; machineId: string | null; turns: Turn[]; updatedAt: string }`.
  - `conversationsReducer(state, action)` actions: `new`, `select`, `appendUser`, `appendPending`, `resolve`, `fail`, `loaded`.
  - `toHistory(turns: Turn[]): ConversationMessage[]` — user turns verbatim; done assistant turns → `response.diagnostic?.incident_summary ?? response.error ?? "No diagnostic returned."`; pending/error turns excluded.
  - `withMachineContext(text: string, machineId: string | null): string` — returns text unchanged if `machineId` null or text contains `machineId` (case-insensitive, word boundary); else `"[Machine {machineId}] " + text`.
  - `loadConversations(tenantId, userId): Conversation[]`, `saveConversations(tenantId, userId, list)` — try/catch, cap 20 (drop oldest by `updatedAt`).
  - `useConversation(): { active: Conversation; list: Conversation[]; send(text: string): Promise<void>; retry(turnId: string): Promise<void>; newConversation(): void; select(id: string): void; sending: boolean }`.
  - Title = first user message, truncated to 60 chars.
- Composer: textarea, `maxLength=10000`, send disabled when trimmed length < 3 or `sending`; Enter sends, Shift+Enter newline; quick chips insert text (exact: `Show recent sensor readings`, `Similar past incidents`, `Relevant manual section`, `Downtime cost if stopped`) without sending; machine chip opens `MachineSelector`; mic button rendered only if `window.SpeechRecognition || window.webkitSpeechRecognition`, appends transcript; disclaimer exact copy from Global Constraints.
- In-flight request is tied to `{conversationId, tenantId, userId}`; a response whose key no longer matches the active key is discarded (resolves nothing).

- [ ] **Step 1: Write failing tests**:
  - `toHistory uses incident_summary for assistant turns and skips pending`.
  - `withMachineContext prefixes only when machine not mentioned` — `("noise on a2", "A2")` unchanged; `("grinding noise", "A2")` → `"[Machine A2] grinding noise"`.
  - `saveConversations caps at 20` and `loadConversations survives throwing storage` (stub `localStorage.getItem` to throw → `[]`).
  - `Composer disables send under 3 chars`, `chip inserts text without sending`, `mic hidden when unsupported`.
  - `send appends user + pending then resolves with response` (mock diagnose → `diagnoseCompleted`), request body `conversation_history` equals `toHistory` of prior turns.
  - `send failure becomes error turn with retry` (mock reject `ApiError("Could not reach the server.")`); `retry` resends `retryText`.
  - `response after identity switch is discarded` — start send, switch identity, resolve → new active conversation has 0 turns.
- [ ] **Step 2: Run** `pnpm -C web test` → FAIL.
- [ ] **Step 3: Implement.** Pending assistant turn copy: `Checking machine data…`.
- [ ] **Step 4: Run** lint, typecheck, test → pass.
- [ ] **Step 5: Commit** `feat(web): conversation state, composer and send flow`

### Task 6: Assistant turn rendering

**Files:**
- Create: `web/src/components/{AssistantTurn,ToolTrace,DiagnosisCard,ConfidenceBars,EvidenceList,ActionSteps,MissingInfo,SafetyBanner}.tsx`
- Test: `web/src/components/AssistantTurn.test.tsx`

**Interfaces:**
- Consumes: `Turn` (Task 5), fixtures (Task 3), `selected` machine (Task 4) for downtime chip.
- Produces: `AssistantTurn({ turn, machine, onDraftWorkOrder, onRetry }: { turn: Turn & {role:"assistant"}; machine: MachineSummary | null; onDraftWorkOrder(): void; onRetry(): void })`; renders `ApprovalCard` slot from Task 7 when `response.pending_approval` is set.
- Rendering rules:
  - Header: `Maintain AI` + exact status copy; timestamp mono.
  - `ToolTrace`: collapsed by default, label `Used {n} tools`, each item `tool_name`, status icon (`ok`/`completed` → check, else warning), `{latency_ms} ms`; hidden when `tool_trace` empty.
  - `DiagnosisCard`: `incident_summary`; first cause as "Likely cause" callout with its `reasoning_summary`; other causes listed as "Alternatives"; `ConfidenceBars` low=1, medium=3, high=5 of 5 filled + word.
  - `EvidenceList`: each observation → card with icon by `source_type` (manual `menu_book`, incident_history `history`, tool `sensors`, user `person`), `statement` in quotes, `source_reference` mono. Phone: horizontal snap carousel; `md+`: 3-column grid.
  - `ActionSteps`: ordered by `step`, rows min-h 56px, badges `Requires shutdown` / `Requires approval` when true.
  - `MissingInfo`: shown only when non-empty, heading `Missing information`.
  - `SafetyBanner`: heading `Safety`, body `safety_notice` verbatim.
  - Downtime chip: `~{currency}{hourly_downtime_cost}/hr if stopped · {criticality} criticality` from selected machine, omitted when machine null.
  - Actions: `Draft work order` (calls `onDraftWorkOrder`, which sends `Please propose a draft work order for machine {id} based on this diagnosis.`), `Ask follow-up` (focuses composer), run id link (`Run {first 8 chars}`; href `${VITE_DASHBOARD_URL}?run_id=…` if set, else copies id).
  - Error state (`state:"error"` or `response.status !== "completed"` with null diagnostic): message text, run id if present, `Retry` button.

- [ ] **Step 1: Write failing tests** with `diagnoseCompleted`/`diagnoseFailed`:
  - `renders likely cause, alternatives and confidence word`.
  - `renders evidence with source references`.
  - `renders steps in order with shutdown badge`.
  - `renders safety notice verbatim and missing information`.
  - `tool trace collapsed shows count, expands on click`.
  - `failed response shows error and run id, no diagnosis card`.
  - `never renders forbidden strings` — container text matches none of `/SCADA|Emergency|Dispatch|Live stream/i`, and no `/\b0\.\d{2}\b/` confidence pattern.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** lint, typecheck, test → pass.
- [ ] **Step 5: Commit** `feat(web): render diagnostic responses`

### Task 7: Work-order approval card

**Files:**
- Create: `web/src/components/ApprovalCard.tsx`
- Test: `web/src/components/ApprovalCard.test.tsx`

**Interfaces:**
- Consumes: `PendingApproval`, `ApiClient.decideApproval` (Task 3).
- Produces: `ApprovalCard({ approval, client }: { approval: PendingApproval; client: ApiClient })`. Internal state: `idle | submitting | approved(result) | rejected | error(message)`; `idempotencyKey = crypto.randomUUID()` created once per card (useRef) and reused for retries.
- Shows `approval.message`, and from `proposed_action` only keys present among `machine_id`, `title`, `description`, `priority` (labels `Machine`, `Title`, `Description`, `Priority`). Buttons `Approve & create draft` (56px, primary), `Reject`. Footer exact copy. After approve: `Draft created` + `result.work_order_id` when present; after reject: `Rejected`.

- [ ] **Step 1: Write failing tests**:
  - `approve sends approved:true with idempotency key and shows work order id`.
  - `double tap sends one request` — two quick clicks → `decideApproval` called once.
  - `retry after error reuses idempotency key` — first call rejects, click again → same key.
  - `reject shows Rejected and disables buttons`.
  - `renders only proposed_action fields that exist`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; wire into `AssistantTurn`.
- [ ] **Step 4: Run** lint, typecheck, test → pass. Manual: with API + demo provider, ask about A1 E217, request a draft work order, approve → `Draft created`.
- [ ] **Step 5: Commit** `feat(web): human approval card for draft work orders`

### Task 8: Build, container, CI and docs

**Files:**
- Modify: `Dockerfile`, `.github/workflows/ci.yml`, `README.md`

**Interfaces:**
- Dockerfile: new first stage `FROM node:22-slim AS web` → `corepack enable`, copy `web/package.json web/pnpm-lock.yaml`, `pnpm install --frozen-lockfile`, copy `web/`, `pnpm build`. Runtime stage: `COPY --from=web /web/dist ./web/dist`.
- CI: job `web` (ubuntu-latest, timeout 10): checkout, `pnpm/action-setup@v4` (version 9), `actions/setup-node@v4` (node 22, cache pnpm, `cache-dependency-path: web/pnpm-lock.yaml`), then in `web/`: `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`.
- README: section "Technician chat app" — dev (`uvicorn app.main:app` + `pnpm -C web dev`, open `http://localhost:5173/app/`), prod (`pnpm -C web build`, open `http://localhost:8000/app/`), note identity is demo-only and app is read-only decision support.

- [ ] **Step 1: Implement** the three changes.
- [ ] **Step 2: Verify** `docker build -t maintain-ai:web .` succeeds; `docker run -p 8000:8000 maintain-ai:web` → `GET /app/` 200.
- [ ] **Step 3: Manual responsive check** at 390, 768, 1024, 1440 px against `.stitch/designs/*.png`: layout regions match spec §2 table; no horizontal page scroll; every interactive element ≥ 48px.
- [ ] **Step 4: Run** full suite: `pytest -m "not live" -q`, ruff, mypy, `pnpm -C web lint typecheck test build`.
- [ ] **Step 5: Commit** `build: ship web app in container and CI`
