# Provider-Neutral Conversation + Claude Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace OpenAI-shaped conversation dicts with app-owned typed items, keep OpenAI working through a translating adapter, and add a Claude adapter selectable with `LLM_PROVIDER=anthropic`.

**Architecture:** `app/llm/base.py` owns `UserMessage | AssistantMessage | ToolCall | ToolResult` and `ToolSpec`. The orchestrator, DemoProvider and eval harness speak only these. Each vendor adapter translates to and from its SDK. Claude returns its final `DiagnosticResult` through a forced `submit_diagnostic` tool.

**Tech Stack:** Python 3.12, FastAPI, pydantic 2, pytest, mypy, ruff, `openai` SDK, `anthropic` SDK.

**Spec:** `docs/superpowers/specs/2026-11-21-anthropic-provider-design.md`

## Global Constraints

- No behaviour change visible to technicians; all existing tests stay green (token *estimates* may change only where derived from serialized length).
- No network in tests; SDK clients are injected fakes. SDK internal retries stay off (`max_retries=0`).
- `LLM_PROVIDER` values: `demo`, `openai`, `anthropic`.
- Claude defaults documented in `.env.example`: `DEFAULT_MODEL=claude-sonnet-5-5`, `SMALL_MODEL=claude-haiku-5-5`.
- Final-answer tool name: `submit_diagnostic`; `tool_choice={"type": "any"}`.
- Tool results keep today's untrusted envelope JSON exactly (`trust_boundary`, `instruction_policy`, `tool_result`).
- Secrets never logged; tenant id never sent to a vendor.
- Lint/type gates: `ruff check .`, `ruff format --check .`, `mypy app dashboard evals scripts`, `pytest -m "not live"`.

## Review Focus

1. Claude replies with plain text and no tool call (ignores `tool_choice`) → treated as invalid model output, not a crash. (Task 3 test `test_text_only_reply_has_no_output_text`.)
2. Claude returns a `tool_use` input that is not a dict / final answer that fails the schema → loop's existing invalid-output path handles it. (Task 3 test `test_final_answer_passes_raw_json_through`.)
3. Conversation starts with an assistant item (context-omission notice) → Anthropic requires the first message to be `user`; adapter must still produce a valid sequence. (Task 3 test `test_leading_assistant_message_is_preceded_by_user`.)
4. Out-of-credit / 401 errors → non-retryable, clear message; 529 overloaded → retryable. (Task 3 test `test_error_mapping`.)
5. OpenAI adapter after refactor sends byte-equivalent request payloads to before. (Task 2 test `test_openai_payload_matches_responses_shape`.)

---

## File Structure

```
app/llm/base.py                 neutral items, ToolSpec, helpers; ProviderRequest/Response use them
app/tools/base.py               ToolDefinition.spec() -> ToolSpec (replaces provider_schema)
app/tools/registry.py           tool_specs (replaces provider_schemas)
app/agent/orchestrator.py       builds/extends neutral conversation
app/llm/demo_provider.py        reads/writes neutral items
app/llm/openai_provider.py      neutral <-> Responses translation
app/llm/anthropic_provider.py   NEW: neutral <-> Messages translation
app/llm/factory.py, app/config.py, pyproject.toml, .env.example, config/model_pricing.yaml, README.md
evals/runner.py, evals/scenario.py
tests/test_llm_base.py (new), tests/test_openai_provider.py, tests/test_anthropic_provider.py (new),
tests/test_agent.py, tests/test_demo_provider.py, others touching input_items/provider_schemas
```

---

### Task 1: Neutral conversation types and tool specs

**Files:** Modify `app/llm/base.py`, `app/tools/base.py`, `app/tools/registry.py`; Test `tests/test_llm_base.py`

**Interfaces — Produces:**
- `UserMessage(text: str)`, `AssistantMessage(text: str)`, `ToolCall(call_id: str, name: str, arguments: str)`, `ToolResult(call_id: str, output: str)` — frozen slotted dataclasses; `ConversationItem` union; `ProviderToolCall = ToolCall`.
- `ToolSpec(name: str, description: str, parameters: dict[str, Any])`.
- `conversation_to_jsonable(items: Sequence[ConversationItem]) -> list[dict[str, Any]]` — each item → `{"kind": "user_message"|"assistant_message"|"tool_call"|"tool_result", ...fields}`.
- `conversation_characters(items) -> int` = `len(json.dumps(conversation_to_jsonable(items), ensure_ascii=False))`.
- `ToolDefinition.spec() -> ToolSpec` (parameters = existing strict-normalised schema); `ToolRegistry.tool_specs -> list[ToolSpec]`. Keep `provider_schema(s)` until Task 2.

- [ ] Step 1: tests `test_conversation_to_jsonable_kinds`, `test_conversation_characters_counts_serialized_length`, `test_tool_spec_matches_strict_schema` (spec.parameters == definition.provider_schema()["parameters"] for every registry tool).
- [ ] Step 2: run `python -m pytest tests/test_llm_base.py -q` → FAIL (import errors).
- [ ] Step 3: implement.
- [ ] Step 4: run full suite + ruff + mypy → green.
- [ ] Step 5: commit `refactor(llm): add provider-neutral conversation types and tool specs`.

### Task 2: Move loop, demo provider, evals and OpenAI adapter onto neutral items

**Files:** Modify `app/llm/base.py` (ProviderRequest/Response fields), `app/agent/orchestrator.py`, `app/llm/demo_provider.py`, `app/llm/openai_provider.py`, `app/tools/base.py`, `app/tools/registry.py`, `evals/runner.py`, `evals/scenario.py`, affected tests.

**Interfaces — Produces:**
- `ProviderRequest(model, instructions, conversation: list[ConversationItem], tools: list[ToolSpec], output_schema, max_output_tokens, trusted_tenant_id=None)`.
- `ProviderResponse(request_id, output_text, tool_calls: list[ToolCall], items: list[ConversationItem], usage, metadata={})`.
- `openai_provider.to_responses_input(items) -> list[dict]` (`UserMessage/AssistantMessage` → `{"role","content"}`, `ToolCall` → `{"type":"function_call","call_id","name","arguments"}`, `ToolResult` → `{"type":"function_call_output","call_id","output"}`); `to_responses_tools(specs) -> list[dict]` (`{"type":"function","name","description","parameters","strict":True}`); output: `function_call` → `ToolCall`, non-empty `output_text` → `AssistantMessage`.
- Orchestrator `_tool_output(call_id, result) -> ToolResult` (same envelope text). `_provider_request_characters` uses `conversation_characters` and `json.dumps` of `[asdict(spec) ...]`.
- `provider_schema`/`provider_schemas` removed; all callers use `spec`/`tool_specs`.

- [ ] Step 1: tests in `tests/test_openai_provider.py`: `test_openai_payload_matches_responses_shape` (fake client captures kwargs; input list equals the dict shapes above for a conversation of user/tool_call/tool_result/assistant; tools equal the function-tool dicts; `text.format` json_schema strict unchanged), `test_openai_output_maps_to_neutral_items`. Update existing tests that build `ProviderRequest(input_items=...)`/read `output_items` to the new fields.
- [ ] Step 2: run → FAIL.
- [ ] Step 3: implement; DemoProvider reads `isinstance(item, ToolResult)` etc., emits `ToolCall`s or one `AssistantMessage`; usage estimates use `conversation_characters` and `conversation_to_jsonable` of its output.
- [ ] Step 4: full suite, ruff, ruff format, mypy, scenario eval smoke (`python -m evals.runner --dataset evals/cases/v1.json --backend scenario --mode optimized --limit 3 --output evals/reports/ci-scenario.actual.json`) → green.
- [ ] Step 5: commit `refactor(llm): run the agent loop on provider-neutral items`.

### Task 3: Claude adapter

**Files:** Create `app/llm/anthropic_provider.py`, `tests/test_anthropic_provider.py`; Modify `app/config.py`, `app/llm/factory.py`, `pyproject.toml`, `.env.example`, `config/model_pricing.yaml`.

**Interfaces — Produces:**
- `AnthropicMessagesProvider(settings: Settings, client: Any | None = None)`, `name = "anthropic"`; raises `ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")` without key.
- `FINAL_TOOL = "submit_diagnostic"`.
- `to_anthropic_messages(items) -> list[dict]`, `to_anthropic_tools(specs, output_schema) -> list[dict]`.
- Settings: `llm_provider: Literal["demo","openai","anthropic"]`, `anthropic_api_key: SecretStr | None`, `anthropic_base_url: str | None`.

- [ ] Step 1: tests (fake client whose `messages.create` records kwargs and returns scripted objects):
  - `test_tools_include_final_answer_tool_and_force_tool_use` — tools = specs as `{name, description, input_schema}` + `submit_diagnostic` with `input_schema == output_schema`; `tool_choice == {"type":"any"}`; `system == instructions`; `max_tokens == max_output_tokens`.
  - `test_messages_batch_tool_calls_and_results` — `[User, ToolCall a, ToolCall b, ToolResult a, ToolResult b]` → `[user text, assistant[tool_use a, tool_use b], user[tool_result a, tool_result b]]`, `input` parsed from arguments.
  - `test_adjacent_same_role_messages_merge` and `test_leading_assistant_message_is_preceded_by_user`.
  - `test_final_answer_becomes_output_text` — `tool_use submit_diagnostic {...}` → `output_text == json.dumps(input)`, `tool_calls == []`, `items == [AssistantMessage(output_text)]`.
  - `test_final_answer_passes_raw_json_through` — non-dict input still serialised (loop validates).
  - `test_real_tools_win_over_final_answer`.
  - `test_text_only_reply_has_no_output_text` — text block only → `output_text == ""`, no tool calls.
  - `test_usage_mapping` — input/output/cache_read/cache_creation tokens.
  - `test_error_mapping` — timeout→`ProviderTimeoutError`; connection, 429, 500, 529→`ProviderTransientError`; 400 with `credit balance` text→`ProviderError` message containing `insufficient credit`; 401→`ProviderError` containing `authentication failed`.
  - `test_factory_builds_anthropic_provider` and `test_missing_key_is_rejected`.
- [ ] Step 2: run → FAIL.
- [ ] Step 3: `pip install anthropic`; add dependency `anthropic>=0.40,<1` (pin to installed major); implement; verify Claude prices on Anthropic's official pricing page and add `model_pricing.yaml` entries with `source_url` and `verified_at: 2026-11-21`; document model pairs in `.env.example`.
- [ ] Step 4: full suite + gates → green.
- [ ] Step 5: commit `feat(llm): add Claude provider via Anthropic Messages API`.

### Task 4: End-to-end proof and docs

**Files:** Test `tests/test_agent.py` (or new `tests/test_anthropic_agent.py`); Modify `README.md`.

- [ ] Step 1: test `test_orchestrator_completes_with_scripted_claude` — fake client scripted: turn 1 `tool_use get_machine_status {"machine_id":"A2"}`, turn 2 `tool_use submit_diagnostic` with a valid `DiagnosticResult` citing `tool:get_machine_status:A2`; run through `MaintenanceAgent` on the seeded DB → status `completed`, tool trace has `get_machine_status`, usage provider `anthropic`; second request's messages contain the `tool_result` for turn 1.
- [ ] Step 2: run → FAIL until wiring is right; fix.
- [ ] Step 3: README "Use the live OpenAI provider" section becomes "Use a live LLM provider" covering both, with `.env` keys and the ChatGPT-subscription ≠ API-credit note.
- [ ] Step 4: full gates green; manual: with owner's key in `.env`, restart API, one A2 diagnosis in the web app shows a completed diagnosis with tool trace.
- [ ] Step 5: commit `test(llm): prove Claude end to end; document provider switching`.
