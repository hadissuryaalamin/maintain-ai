import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "../api/client";
import {
  conversationsReducer,
  initialConversations,
  loadConversations,
  newId,
  saveConversations,
  toHistory,
  withMachineContext,
  type Conversation,
  type Turn,
} from "./conversations";
import { useIdentity } from "./identity";

interface ConversationValue {
  active: Conversation;
  list: Conversation[];
  sending: boolean;
  send(text: string): Promise<void>;
  retry(turnId: string): Promise<void>;
  newConversation(): void;
  select(id: string): void;
}

const ConversationContext = createContext<ConversationValue | null>(null);

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Try again.";
}

export function ConversationProvider({
  machineId,
  children,
}: {
  machineId: string | null;
  children: ReactNode;
}) {
  const { tenantId, userId, client } = useIdentity();
  const identityKey = `${tenantId}|${userId}`;
  const [state, dispatch] = useReducer(conversationsReducer, undefined, () =>
    initialConversations(loadConversations(tenantId, userId)),
  );
  const [owner, setOwner] = useState(identityKey);
  const currentKey = useRef(identityKey);
  const inFlight = useRef(new Set<AbortController>());

  // Identity switch: cancel requests, swap to that identity's stored conversations.
  useEffect(() => {
    if (currentKey.current === identityKey) return;
    currentKey.current = identityKey;
    inFlight.current.forEach((controller) => controller.abort());
    inFlight.current.clear();
    dispatch({ type: "loaded", list: loadConversations(tenantId, userId) });
    setOwner(identityKey);
  }, [identityKey, tenantId, userId]);

  useEffect(() => {
    if (owner === identityKey) saveConversations(tenantId, userId, state.list);
  }, [state.list, owner, identityKey, tenantId, userId]);

  useEffect(() => {
    const controllers = inFlight.current;
    return () => controllers.forEach((controller) => controller.abort());
  }, []);

  const active = useMemo(
    () => state.list.find((conversation) => conversation.id === state.activeId) ?? state.list[0]!,
    [state],
  );

  const run = useCallback(
    async (conversationId: string, text: string, history: Turn[], conversationMachine: string | null) => {
      const requestKey = currentKey.current;
      const turnId = newId();
      dispatch({ type: "appendPending", conversationId, turnId, at: new Date().toISOString() });
      const controller = new AbortController();
      inFlight.current.add(controller);
      try {
        const response = await client.diagnose(
          {
            message: withMachineContext(text, conversationMachine),
            conversation_history: toHistory(history),
          },
          controller.signal,
        );
        if (currentKey.current !== requestKey) return;
        dispatch({ type: "resolve", conversationId, turnId, response });
      } catch (error) {
        if (controller.signal.aborted || currentKey.current !== requestKey) return;
        dispatch({ type: "fail", conversationId, turnId, message: errorMessage(error), retryText: text });
      } finally {
        inFlight.current.delete(controller);
      }
    },
    [client],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (trimmed.length < 3) return;
      // The machine shown in the header is the machine the technician is talking about.
      const conversationMachine = machineId ?? active.machineId;
      if (conversationMachine !== active.machineId) {
        dispatch({ type: "setMachine", conversationId: active.id, machineId: conversationMachine });
      }
      const history = active.turns;
      dispatch({
        type: "appendUser",
        conversationId: active.id,
        turn: { id: newId(), role: "user", text: trimmed, at: new Date().toISOString() },
      });
      await run(active.id, trimmed, history, conversationMachine);
    },
    [active, machineId, run],
  );

  const retry = useCallback(
    async (turnId: string) => {
      const index = active.turns.findIndex((turn) => turn.id === turnId);
      const turn = active.turns[index];
      if (!turn || turn.role !== "assistant" || turn.state !== "error") return;
      dispatch({ type: "removeTurn", conversationId: active.id, turnId });
      const before = active.turns.slice(0, index);
      const lastUser = before.length - 1;
      const history = before[lastUser]?.role === "user" ? before.slice(0, lastUser) : before;
      await run(active.id, turn.retryText, history, machineId ?? active.machineId);
    },
    [active, machineId, run],
  );

  const sending = active.turns.some((turn) => turn.role === "assistant" && turn.state === "pending");

  const value = useMemo<ConversationValue>(
    () => ({
      active,
      list: state.list,
      sending,
      send,
      retry,
      newConversation: () => dispatch({ type: "new" }),
      select: (id: string) => dispatch({ type: "select", id }),
    }),
    [active, state.list, sending, send, retry],
  );

  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export function useConversation(): ConversationValue {
  const value = useContext(ConversationContext);
  if (!value) throw new Error("useConversation must be used inside ConversationProvider");
  return value;
}
