import { describe, expect, it, vi } from "vitest";
import { diagnoseCompleted, diagnoseFailed } from "../test/fixtures";
import {
  MAX_CONVERSATIONS,
  conversationsReducer,
  emptyConversation,
  initialConversations,
  loadConversations,
  saveConversations,
  storageKey,
  toHistory,
  withMachineContext,
  type Conversation,
  type Turn,
} from "./conversations";

const at = "2026-11-21T06:00:00Z";

describe("toHistory", () => {
  it("uses incident_summary for assistant turns and skips pending/error", () => {
    const turns: Turn[] = [
      { id: "1", role: "user", text: "Noise on A2", at },
      { id: "2", role: "assistant", at, state: "done", response: diagnoseCompleted },
      { id: "3", role: "user", text: "And now?", at },
      { id: "4", role: "assistant", at, state: "done", response: diagnoseFailed },
      { id: "5", role: "assistant", at, state: "error", message: "x", retryText: "y" },
      { id: "6", role: "assistant", at, state: "pending" },
    ];
    expect(toHistory(turns)).toEqual([
      { role: "user", content: "Noise on A2" },
      { role: "assistant", content: diagnoseCompleted.diagnostic!.incident_summary },
      { role: "user", content: "And now?" },
      { role: "assistant", content: "Model request failed safely." },
    ]);
  });
});

describe("withMachineContext", () => {
  it("prefixes only when the machine is not mentioned", () => {
    expect(withMachineContext("noise on a2", "A2")).toBe("noise on a2");
    expect(withMachineContext("grinding noise", "A2")).toBe("[Machine A2] grinding noise");
    expect(withMachineContext("pump A22 noise", "A2")).toBe("[Machine A2] pump A22 noise");
    expect(withMachineContext("grinding noise", null)).toBe("grinding noise");
  });

  it("leaves explicit prediction requests untouched", () => {
    const json = '{"type":"L","air_temp_k":300,"process_temp_k":310,"rpm":1500,"torque_nm":40,"tool_wear_min":100}';
    for (const prefix of ["Prediksi kegagalan menggunakan input berikut:", "Predict failure", "please predict machine failure", "Failure prediction", "predict_failure_risk"]) {
      const text = `${prefix}
${json}`;
      expect(withMachineContext(text, "A2")).toBe(text);
    }
  });
});

describe("storage", () => {
  const conversation = (id: string, updatedAt: string): Conversation => ({
    ...emptyConversation(),
    id,
    updatedAt,
    turns: [{ id: `${id}-u`, role: "user", text: "hello there", at: updatedAt }],
  });

  it("saveConversations caps at MAX_CONVERSATIONS keeping the newest", () => {
    const list = Array.from({ length: MAX_CONVERSATIONS + 5 }, (_, index) =>
      conversation(`c${index}`, new Date(Date.UTC(2026, 0, 1, 0, index)).toISOString()),
    );
    saveConversations("company-a", "user-a-tech", list);
    const loaded = loadConversations("company-a", "user-a-tech");
    expect(loaded).toHaveLength(MAX_CONVERSATIONS);
    expect(loaded.some((item) => item.id === "c0")).toBe(false);
    expect(loaded.some((item) => item.id === `c${MAX_CONVERSATIONS + 4}`)).toBe(true);
  });

  it("does not persist empty conversations or pending turns", () => {
    const pending: Conversation = {
      ...conversation("p", at),
      turns: [
        { id: "u", role: "user", text: "hi there", at },
        { id: "a", role: "assistant", at, state: "pending" },
      ],
    };
    saveConversations("company-a", "user-a-tech", [emptyConversation(), pending]);
    const loaded = loadConversations("company-a", "user-a-tech");
    expect(loaded).toHaveLength(1);
    expect(loaded[0]!.turns).toHaveLength(1);
  });

  it("is keyed by tenant and user", () => {
    saveConversations("company-a", "user-a-tech", [conversation("a", at)]);
    expect(loadConversations("company-b", "user-b-tech")).toEqual([]);
    expect(storageKey("company-a", "user-a-tech")).toBe(
      "maintain-ai:conversations:company-a:user-a-tech",
    );
  });

  it("loadConversations survives throwing storage", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadConversations("company-a", "user-a-tech")).toEqual([]);
    spy.mockRestore();
  });

  it("saveConversations survives throwing storage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => saveConversations("company-a", "user-a-tech", [conversation("a", at)])).not.toThrow();
    spy.mockRestore();
  });

  it("ignores corrupt stored data", () => {
    localStorage.setItem(storageKey("company-a", "user-a-tech"), "{not json");
    expect(loadConversations("company-a", "user-a-tech")).toEqual([]);
  });
});

describe("conversationsReducer", () => {
  it("titles a conversation from its first user message, truncated to 60 chars", () => {
    const state = initialConversations([]);
    const text = "x".repeat(80);
    const next = conversationsReducer(state, {
      type: "appendUser",
      conversationId: state.activeId,
      turn: { id: "u1", role: "user", text, at },
    });
    expect(next.list[0]!.title).toBe(`${"x".repeat(59)}…`);
  });

  it("resolve replaces the pending turn", () => {
    let state = initialConversations([]);
    const id = state.activeId;
    state = conversationsReducer(state, { type: "appendPending", conversationId: id, turnId: "a1", at });
    state = conversationsReducer(state, {
      type: "resolve",
      conversationId: id,
      turnId: "a1",
      response: diagnoseCompleted,
    });
    const turn = state.list[0]!.turns[0]!;
    expect(turn.role === "assistant" && turn.state).toBe("done");
  });
});
