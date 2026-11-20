import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient, type Identity } from "../api/client";
import type { DiagnoseResponse } from "../api/types";
import { diagnoseCompleted, diagnoseFailed } from "../test/fixtures";
import { ConversationProvider, useConversation } from "./ConversationProvider";
import { IdentityProvider, useIdentity } from "./identity";

function fakeClient(diagnose: ApiClient["diagnose"]): ApiClient {
  return {
    listMachines: vi.fn().mockResolvedValue([]),
    getMachineSensors: vi.fn(),
    diagnose,
    decideApproval: vi.fn(),
  };
}

function setup(factory: (identity: Identity) => ApiClient, machineId: string | null = "A2") {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <IdentityProvider initial={{ tenantId: "company-a", userId: "user-a-tech" }} clientFactory={factory}>
      <ConversationProvider machineId={machineId}>{children}</ConversationProvider>
    </IdentityProvider>
  );
  return renderHook(() => ({ conversation: useConversation(), identity: useIdentity() }), { wrapper });
}

describe("ConversationProvider", () => {
  it("send appends user + pending then resolves with response", async () => {
    let resolve: (value: DiagnoseResponse) => void = () => undefined;
    const diagnose = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)));
    const client = fakeClient(diagnose);
    const { result } = setup(() => client);

    let sending: Promise<void> = Promise.resolve();
    act(() => {
      sending = result.current.conversation.send("Grinding noise since 06:40");
    });
    expect(result.current.conversation.active.turns.map((t) => t.role)).toEqual(["user", "assistant"]);
    expect(result.current.conversation.sending).toBe(true);
    expect(diagnose).toHaveBeenCalledWith(
      { message: "[Machine A2] Grinding noise since 06:40", conversation_history: [] },
      expect.anything(),
    );

    await act(async () => {
      resolve(diagnoseCompleted);
      await sending;
    });
    const last = result.current.conversation.active.turns[1]!;
    expect(last.role === "assistant" && last.state).toBe("done");
    expect(result.current.conversation.sending).toBe(false);
    expect(result.current.conversation.active.title).toBe("Grinding noise since 06:40");
  });

  it("sends prior turns as conversation_history", async () => {
    const diagnose = vi.fn().mockResolvedValue(diagnoseCompleted);
    const { result } = setup(() => fakeClient(diagnose));
    await act(() => result.current.conversation.send("First question on A2"));
    await act(() => result.current.conversation.send("And the suction?"));
    expect(diagnose.mock.calls[1]![0].conversation_history).toEqual([
      { role: "user", content: "First question on A2" },
      { role: "assistant", content: diagnoseCompleted.diagnostic!.incident_summary },
    ]);
  });

  it("send failure becomes error turn with retry", async () => {
    const diagnose = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("Could not reach the server.", null))
      .mockResolvedValueOnce(diagnoseCompleted);
    const { result } = setup(() => fakeClient(diagnose));
    await act(() => result.current.conversation.send("Pump A2 noise"));
    const failed = result.current.conversation.active.turns[1]!;
    expect(failed.role === "assistant" && failed.state).toBe("error");
    expect(failed.role === "assistant" && failed.state === "error" && failed.message).toBe(
      "Could not reach the server.",
    );

    await act(() => result.current.conversation.retry(failed.id));
    expect(diagnose).toHaveBeenCalledTimes(2);
    expect(diagnose.mock.calls[1]![0]).toEqual({ message: "Pump A2 noise", conversation_history: [] });
    const turns = result.current.conversation.active.turns;
    expect(turns).toHaveLength(2);
    expect(turns[1]!.role === "assistant" && turns[1]!.state).toBe("done");
  });

  it("retry works on a completed-but-failed run", async () => {
    const diagnose = vi
      .fn()
      .mockResolvedValueOnce(diagnoseFailed)
      .mockResolvedValueOnce(diagnoseCompleted);
    const { result } = setup(() => fakeClient(diagnose));
    await act(() => result.current.conversation.send("Pump A2 noise"));
    const failed = result.current.conversation.active.turns[1]!;
    await act(() => result.current.conversation.retry(failed.id));
    expect(diagnose).toHaveBeenCalledTimes(2);
    expect(diagnose.mock.calls[1]![0]).toEqual({ message: "Pump A2 noise", conversation_history: [] });
    const turns = result.current.conversation.active.turns;
    expect(turns).toHaveLength(2);
    expect(turns[1]!.role === "assistant" && turns[1]!.state === "done" && turns[1]!.response.status).toBe(
      "completed",
    );
  });

  it("ignores a second send while a request is pending", async () => {
    let resolve: (value: DiagnoseResponse) => void = () => undefined;
    const diagnose = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)));
    const { result } = setup(() => fakeClient(diagnose));
    act(() => {
      void result.current.conversation.send("Draft a work order for A2");
    });
    await act(() => result.current.conversation.send("Draft a work order for A2"));
    expect(diagnose).toHaveBeenCalledTimes(1);
    await act(async () => resolve(diagnoseCompleted));
  });

  it("response after identity switch is discarded", async () => {
    let resolve: (value: DiagnoseResponse) => void = () => undefined;
    const diagnose = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)));
    const { result } = setup(() => fakeClient(diagnose));
    act(() => {
      void result.current.conversation.send("Noise on A2 pump");
    });
    act(() => result.current.identity.setIdentity("company-b", "user-b-tech"));
    await waitFor(() => expect(result.current.conversation.active.turns).toHaveLength(0));
    await act(async () => resolve(diagnoseCompleted));
    expect(result.current.conversation.active.turns).toHaveLength(0);
    expect(result.current.conversation.list.every((c) => c.turns.length === 0)).toBe(true);
  });

  it("keeps working when localStorage throws", async () => {
    const getSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = setup(() => fakeClient(vi.fn().mockResolvedValue(diagnoseCompleted)));
    await act(() => result.current.conversation.send("Noise on A2 pump"));
    expect(result.current.conversation.active.turns).toHaveLength(2);
    getSpy.mockRestore();
    setSpy.mockRestore();
  });

  it("restores saved conversations for the identity", async () => {
    const diagnose = vi.fn().mockResolvedValue(diagnoseCompleted);
    const first = setup(() => fakeClient(diagnose));
    await act(() => first.result.current.conversation.send("Saved question for A2"));
    first.unmount();
    const second = setup(() => fakeClient(diagnose));
    expect(second.result.current.conversation.list.map((c) => c.title)).toContain("Saved question for A2");
  });
});
