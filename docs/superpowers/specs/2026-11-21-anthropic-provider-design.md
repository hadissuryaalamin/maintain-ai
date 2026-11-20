# Provider-Neutral Conversation Format and Claude Provider — Design

Date: 2026-11-21
Status: Approved 2026-11-21 (owner chose the provider-neutral route; technical details are the
builder's calls, listed at the end)

## Intent

The project owner wants maintain-ai to answer with a real LLM in demos and to switch LLM
vendors (Claude now; ChatGPT, DeepSeek later) by changing `.env` only. The OpenAI account has
no API credit; the owner has an Anthropic API key. The owner also wants the code to treat
every vendor equally: the app keeps its own conversation format, and each vendor gets a
translator (adapter). Nothing changes on screen.

## Goals

1. A provider-neutral conversation format owned by the app replaces the OpenAI Responses item
   dicts used inside the agent loop, the demo provider and the evaluation harness.
2. The OpenAI adapter translates neutral ⇄ Responses API; behaviour unchanged.
3. A new Claude adapter translates neutral ⇄ Anthropic Messages API.
4. Every provider's final answer is the same `DiagnosticResult` JSON contract, then the same
   validation, grounding, safety policy, telemetry and web rendering.
5. `LLM_PROVIDER=demo|openai|anthropic` plus model names in `.env` select the vendor.

## Non-goals

- Model selection from the web app.
- DeepSeek / Chat Completions adapter (later; the neutral format is designed to allow it).
- Streaming, prompt-caching tuning, extended thinking.

## Anti-goals

- Any change in what technicians see or in the safety/grounding/approval behaviour.
- Provider-specific shortcuts that skip validation.
- New places where secrets, tenant context or prompt text are logged or transmitted.
- Paid API calls in CI or unit tests.

## Approaches considered

| Decision | Options | Chosen |
|---|---|---|
| Internal conversation format | keep OpenAI Responses dicts (adapters translate from OpenAI shape) / **app-owned format** | App-owned format — owner's choice ("the tidy route") |
| Shape of the app-owned format | **typed dataclasses** / neutral dicts with own keys | Typed dataclasses — mypy catches misuse; builder's call |
| Forcing Claude's final JSON | **final-answer tool `submit_diagnostic`** / native structured-output parameter / prompt-only JSON / second LLM extracting JSON from prose | Final-answer tool — reliable across Claude models and SDK versions |

## Design

### 1. Neutral types (`app/llm/base.py`)

```python
@dataclass(frozen=True, slots=True)
class UserMessage:      text: str
class AssistantMessage: text: str
class ToolCall:         call_id: str; name: str; arguments: str   # JSON object text
class ToolResult:       call_id: str; output: str                 # JSON envelope text
ConversationItem = UserMessage | AssistantMessage | ToolCall | ToolResult

class ToolSpec: name: str; description: str; parameters: dict[str, Any]
```

- `ProviderRequest`: `model, instructions, conversation: list[ConversationItem],
  tools: list[ToolSpec], output_schema, max_output_tokens, trusted_tenant_id`.
- `ProviderResponse`: `request_id, output_text, tool_calls: list[ToolCall],
  items: list[ConversationItem]` (what the loop appends to the conversation), `usage, metadata`.
- `ProviderToolCall` stays as an alias of `ToolCall` for existing imports.
- `conversation_characters(items)` and `conversation_to_jsonable(items)` helpers for budgets,
  token estimates and the evaluation harness.
- `ToolDefinition.spec() -> ToolSpec` (strict-normalised JSON Schema, as today);
  `ToolRegistry.tool_specs`. `provider_schemas` is removed.

### 2. Consumers switch to neutral types
- Orchestrator builds `UserMessage`/`AssistantMessage` from history (omission notice is an
  `AssistantMessage`), appends `response.items`, and appends `ToolResult` (same untrusted
  envelope JSON) after each tool call.
- `DemoProvider` reads `ToolResult`, `ToolCall`, `UserMessage` instead of dict keys. Its
  replies are `ToolCall` items or one `AssistantMessage(text=json)`. Token estimates use
  `conversation_characters`.
- `evals/runner.py`, `evals/scenario.py` read neutral items and `tool_specs`.

### 3. OpenAI adapter (translation only)
- In: `UserMessage/AssistantMessage → {"role","content"}`, `ToolCall → function_call`,
  `ToolResult → function_call_output`, `ToolSpec → {"type":"function", name, description,
  parameters, "strict": True}`; same `text.format json_schema strict` request as today.
- Out: `function_call` → `ToolCall`; final text → `AssistantMessage`.

### 4. Claude adapter (`app/llm/anthropic_provider.py`, `AnthropicMessagesProvider`, name `anthropic`)
- In: `instructions → system`; tools → `{name, description, input_schema}` plus
  `submit_diagnostic` with `input_schema = output_schema`; `tool_choice = {"type": "auto"}` plus a
  system-prompt protocol instruction (live testing showed current Claude models reject forced
  `any`/`tool` choice);
  conversation → `messages`: user/assistant text blocks, consecutive `ToolCall`s → one
  assistant message of `tool_use` blocks (`input = json.loads(arguments)`), consecutive
  `ToolResult`s → one user message of `tool_result` blocks; adjacent same-role messages are
  merged (Anthropic requires alternation). `max_tokens = max_output_tokens`; SDK retries off.
- Out: `submit_diagnostic` → `output_text = json.dumps(input)` and an `AssistantMessage`
  item; other `tool_use` → `ToolCall`s (if real tools and the final tool appear together,
  real tools win and the final answer is dropped). Usage maps `input_tokens`,
  `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`.
- A replayed final answer (`AssistantMessage` holding JSON) is sent back as plain assistant
  text.
- Errors: timeout → `ProviderTimeoutError`; connection, 429 rate limit, 5xx, 529 overloaded →
  `ProviderTransientError`; out of credit, auth, other 4xx → `ProviderError` whose message
  names the cause (e.g. "model provider rejected the request: insufficient credit").

### 5. Configuration and wiring
- `llm_provider: Literal["demo", "openai", "anthropic"]`; `anthropic_api_key: SecretStr | None`;
  `anthropic_base_url: str | None`; startup fails clearly if the key is missing.
- `factory.build_provider` adds `anthropic`.
- `pyproject.toml` adds the `anthropic` SDK.
- `.env.example` documents model pairs: openai `gpt-5.6-terra`/`gpt-5.6-luna`; anthropic
  `claude-sonnet-5-5`/`claude-haiku-5-5`.
- `config/model_pricing.yaml`: entries for both Claude models, verified against Anthropic's
  official pricing page at implementation time.

## Testing
- Translation unit tests per adapter with fake SDK clients (no network): message ordering,
  batching, role merging, tool schema mapping, final-answer extraction, mixed turns, usage,
  error mapping.
- Existing orchestrator/demo/eval/OpenAI tests keep passing after the refactor (same
  behaviour); expected token *estimates* in fixtures may change only where they derive from
  serialized length.
- End-to-end orchestrator test with a scripted fake Claude client: tool turn then final answer
  → completed `DiagnoseResponse`.
- Manual: one real A2 diagnosis through the web app with the owner's key.

## Builder's calls
- Typed dataclasses for the neutral format; `provider_schemas` replaced by `tool_specs`.
- Final-answer tool `submit_diagnostic`, `tool_choice: auto` with a protocol instruction (changed
  from `any` after live testing), real tools win in mixed turns; `stop_reason: max_tokens` is a
  clear provider error.
- Default Claude models `claude-sonnet-5-5` / `claude-haiku-5-5`.
- Non-retryable provider rejections get cause-naming messages in the Claude adapter.
