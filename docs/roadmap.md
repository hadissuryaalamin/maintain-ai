# Roadmap

Status as of 2026-11-21. The technician chat app (`web/`), the provider-neutral conversation
format and the OpenAI and Claude adapters are done. The two items below are the main planned
work, in the recommended order: grounding first, so the single frontend can show real model
output and compare providers.

## 1. Model-authored answers with enforced citations (grounding policy)

**Problem.** `app/agent/grounding.py` (`enforce_grounding`) replaces every model-authored field
(incident summary, observations, possible causes, recommended actions, missing information)
with application-authored text built from tool evidence. That is a strict and safe default, but
it means any LLM only chooses *which tools to call*. The answer a technician sees reads the same
for the demo provider, OpenAI and Claude, which hides what a real model adds.

**Goal.** Keep model-written causes, actions and summary when every factual claim cites a source
that was actually produced in that run, and fall back to the current application text when it
does not.

**Direction (to be designed):**
- Accept a model observation only if its `source_reference` matches evidence returned by a tool
  in the same run (or the user's own message); drop the rest and say so in missing information.
- Accept a possible cause only if its reasoning cites at least one accepted source; cap
  confidence when sources are thin (as today).
- Keep the deterministic safety rules unchanged: unsafe actions removed, invasive steps flagged
  `requires_shutdown`, lockout/tagout step and safety notice always present, work orders only
  through the approval gate.
- Prompt instructions telling the model the exact `source_reference` formats to cite.
- Tests per rule; re-run the 30-case evaluation with the demo provider (must stay equivalent)
  and with a live provider (report the difference).

**Success.** The same question answered by Claude and by the demo provider produces visibly
different, model-written but fully cited answers, with no drop in the safety checks.

## 2. One frontend: Insights and run trace in the React app, then remove Streamlit

**Problem.** The project has two frontends. `web/` serves technicians; the Streamlit dashboard
(`dashboard/app.py`) still holds the run-trace view and the cost/quality analytics.

**Goal.** Everything in one React app, then delete Streamlit.

**Scope:**
- **Insights page** using the existing endpoints `GET /api/v1/analytics/summary` and
  `GET /api/v1/analytics/runs`: run count and success rate, cost and tokens by model and
  provider, cost by task type, tool frequency and failure rate, baseline vs optimized
  comparison, recent runs table.
- **Run detail page** using `GET /api/v1/runs/{run_id}`: tool trace (name, status, latency,
  error category), token usage, estimated cost, model/provider, timing, diagnostic.
- Navigation: **Chat** and **Insights** in the sidebar/rail; the "Run xxxx" link under each
  answer opens the run detail page (replaces `VITE_DASHBOARD_URL`).
- Same design system, breakpoints and demo identity as the chat app.
- Remove `dashboard/`, `tests/test_dashboard.py`, the `dashboard` Compose service,
  `COPY dashboard` in the Dockerfile, `streamlit`/`pandas` extras in `pyproject.toml`,
  `dashboard` from the CI mypy step, and update README, CONTRIBUTING and `docs/`.

**Success.** A demo runs end to end in one app: ask in chat, open the run trace, then open
Insights to compare cost and success across providers.

## Smaller follow-ups (from reviews)

- Web app: sensor fetch failure shows "Loading readings…" forever; timeouts reported as
  "Could not reach the server"; failed-run error text sent back as assistant history; thread
  does not scroll when an answer resolves; drawer/sheet need focus trap and restore; fonts and
  icons load from Google at runtime (offline shop floors); approval decisions are not persisted
  across reloads.
- Claude adapter: Anthropic cache-token accounting differs from OpenAI (matters only once
  prompt caching is enabled); 529 overload retry backoff is short.
- OpenAI adapter: reasoning items are not replayed between tool turns; verify with a reasoning
  model once API credit is available.
- Chat Completions adapter (DeepSeek, Groq, OpenRouter, Ollama) on the neutral format.
- Regenerate the committed sample evaluation reports (demo token estimates changed).
- Deployment as one container with HTTPS; real authentication instead of demo headers.
