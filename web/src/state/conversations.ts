import type { ConversationMessage, DiagnoseResponse } from "../api/types";

export type UserTurn = { id: string; role: "user"; text: string; at: string };
export type AssistantTurn =
  | { id: string; role: "assistant"; at: string; state: "pending" }
  | { id: string; role: "assistant"; at: string; state: "done"; response: DiagnoseResponse }
  | { id: string; role: "assistant"; at: string; state: "error"; message: string; retryText: string };
export type Turn = UserTurn | AssistantTurn;

export interface Conversation {
  id: string;
  title: string;
  machineId: string | null;
  turns: Turn[];
  updatedAt: string;
}

export interface ConversationsState {
  list: Conversation[];
  activeId: string;
}

export type ConversationsAction =
  | { type: "new"; conversation?: Conversation }
  | { type: "select"; id: string }
  | { type: "loaded"; list: Conversation[] }
  | { type: "setMachine"; conversationId: string; machineId: string | null }
  | { type: "appendUser"; conversationId: string; turn: UserTurn }
  | { type: "appendPending"; conversationId: string; turnId: string; at: string }
  | { type: "resolve"; conversationId: string; turnId: string; response: DiagnoseResponse }
  | { type: "fail"; conversationId: string; turnId: string; message: string; retryText: string }
  | { type: "removeTurn"; conversationId: string; turnId: string };

export const MAX_CONVERSATIONS = 20;
export const TITLE_LIMIT = 60;
export const UNTITLED = "New conversation";

export function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function emptyConversation(machineId: string | null = null): Conversation {
  return { id: newId(), title: UNTITLED, machineId, turns: [], updatedAt: new Date().toISOString() };
}

export function titleFrom(text: string): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > TITLE_LIMIT ? `${clean.slice(0, TITLE_LIMIT - 1)}…` : clean;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Mirrors app/prediction_requests.py: prediction requests are recognised only by their prefix,
// and are not tied to a machine, so they must reach the API unchanged.
const PREDICTION_PREFIX =
  /^\s*(?:please\s+)?(?:predict_failure_risk|predict\s+(?:machine\s+)?failure|failure\s+prediction|prediksi\s+kegagalan)\b/i;

export function withMachineContext(text: string, machineId: string | null): string {
  if (!machineId || PREDICTION_PREFIX.test(text.split("{", 1)[0] ?? "")) return text;
  const pattern = new RegExp(`(^|[^A-Za-z0-9_-])${escapeRegExp(machineId)}(?![A-Za-z0-9_])`, "i");
  return pattern.test(text) ? text : `[Machine ${machineId}] ${text}`;
}

/** A response the technician can act on: a diagnostic or an approval to decide. */
export function hasAnswer(response: DiagnoseResponse): boolean {
  return response.diagnostic !== null || response.pending_approval !== null;
}

export function assistantSummary(response: DiagnoseResponse): string {
  return (
    response.diagnostic?.incident_summary ??
    response.pending_approval?.message ??
    response.error ??
    "No diagnostic returned."
  );
}

export function toHistory(turns: Turn[]): ConversationMessage[] {
  const history: ConversationMessage[] = [];
  for (const turn of turns) {
    if (turn.role === "user") history.push({ role: "user", content: turn.text });
    else if (turn.state === "done") history.push({ role: "assistant", content: assistantSummary(turn.response) });
  }
  return history;
}

export function storageKey(tenantId: string, userId: string): string {
  return `maintain-ai:conversations:${tenantId}:${userId}`;
}

function persistable(list: Conversation[]): Conversation[] {
  return list
    .map((conversation) => ({
      ...conversation,
      turns: conversation.turns.filter((turn) => !(turn.role === "assistant" && turn.state === "pending")),
    }))
    .filter((conversation) => conversation.turns.length > 0)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, MAX_CONVERSATIONS);
}

function isConversation(value: unknown): value is Conversation {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Conversation>;
  return typeof item.id === "string" && typeof item.title === "string" && Array.isArray(item.turns);
}

export function loadConversations(tenantId: string, userId: string): Conversation[] {
  try {
    const raw = localStorage.getItem(storageKey(tenantId, userId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? persistable(parsed.filter(isConversation)) : [];
  } catch {
    return [];
  }
}

export function saveConversations(tenantId: string, userId: string, list: Conversation[]): void {
  try {
    localStorage.setItem(storageKey(tenantId, userId), JSON.stringify(persistable(list)));
  } catch {
    // Storage unavailable (private mode, quota): history simply isn't remembered.
  }
}

export function initialConversations(stored: Conversation[], machineId: string | null = null): ConversationsState {
  const fresh = emptyConversation(machineId);
  return { list: [fresh, ...stored], activeId: fresh.id };
}

function update(
  state: ConversationsState,
  conversationId: string,
  change: (conversation: Conversation) => Conversation,
): ConversationsState {
  if (!state.list.some((conversation) => conversation.id === conversationId)) return state;
  return {
    ...state,
    list: state.list.map((conversation) =>
      conversation.id === conversationId
        ? { ...change(conversation), updatedAt: new Date().toISOString() }
        : conversation,
    ),
  };
}

function replaceTurn(conversation: Conversation, turnId: string, turn: Turn): Conversation {
  return { ...conversation, turns: conversation.turns.map((item) => (item.id === turnId ? turn : item)) };
}

export function conversationsReducer(
  state: ConversationsState,
  action: ConversationsAction,
): ConversationsState {
  switch (action.type) {
    case "new": {
      const active = state.list.find((conversation) => conversation.id === state.activeId);
      if (active && active.turns.length === 0 && !action.conversation) return state;
      const conversation = action.conversation ?? emptyConversation(active?.machineId ?? null);
      const rest = state.list.filter((item) => item.turns.length > 0);
      return { list: [conversation, ...rest], activeId: conversation.id };
    }
    case "select":
      return state.list.some((conversation) => conversation.id === action.id)
        ? { list: state.list.filter((item) => item.turns.length > 0 || item.id === action.id), activeId: action.id }
        : state;
    case "loaded":
      return initialConversations(action.list);
    case "setMachine":
      return update(state, action.conversationId, (conversation) => ({ ...conversation, machineId: action.machineId }));
    case "appendUser":
      return update(state, action.conversationId, (conversation) => ({
        ...conversation,
        title: conversation.title === UNTITLED ? titleFrom(action.turn.text) : conversation.title,
        turns: [...conversation.turns, action.turn],
      }));
    case "appendPending":
      return update(state, action.conversationId, (conversation) => ({
        ...conversation,
        turns: [...conversation.turns, { id: action.turnId, role: "assistant", at: action.at, state: "pending" }],
      }));
    case "resolve":
      return update(state, action.conversationId, (conversation) =>
        replaceTurn(conversation, action.turnId, {
          id: action.turnId,
          role: "assistant",
          at: new Date().toISOString(),
          state: "done",
          response: action.response,
        }),
      );
    case "fail":
      return update(state, action.conversationId, (conversation) =>
        replaceTurn(conversation, action.turnId, {
          id: action.turnId,
          role: "assistant",
          at: new Date().toISOString(),
          state: "error",
          message: action.message,
          retryText: action.retryText,
        }),
      );
    case "removeTurn":
      return update(state, action.conversationId, (conversation) => ({
        ...conversation,
        turns: conversation.turns.filter((turn) => turn.id !== action.turnId),
      }));
  }
}
