import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient, Identity } from "../api/client";
import { IdentityProvider, useIdentity } from "../state/identity";
import { machineA1, machineA2, machineB1, sensorsA2 } from "../test/fixtures";
import { useMachines } from "./useMachines";

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    listMachines: vi.fn().mockResolvedValue([machineA1, machineA2]),
    getMachineSensors: vi.fn().mockResolvedValue(sensorsA2),
    diagnose: vi.fn(),
    decideApproval: vi.fn(),
    ...overrides,
  };
}

function wrapperFor(factory: (identity: Identity) => ApiClient) {
  return ({ children }: { children: ReactNode }) => (
    <IdentityProvider initial={{ tenantId: "company-a", userId: "user-a-tech" }} clientFactory={factory}>
      {children}
    </IdentityProvider>
  );
}

describe("useMachines", () => {
  it("selects first machine and loads its sensors", async () => {
    const client = fakeClient();
    const { result } = renderHook(() => useMachines(), { wrapper: wrapperFor(() => client) });
    await waitFor(() => expect(result.current.sensors).not.toBeNull());
    expect(result.current.selected?.id).toBe("A1");
    expect(client.getMachineSensors).toHaveBeenCalledWith("A1", 12, expect.anything());
  });

  it("select changes machine and fetches its sensors", async () => {
    const client = fakeClient();
    const { result } = renderHook(() => useMachines(), { wrapper: wrapperFor(() => client) });
    await waitFor(() => expect(result.current.selected?.id).toBe("A1"));
    act(() => result.current.select("A2"));
    await waitFor(() =>
      expect(client.getMachineSensors).toHaveBeenLastCalledWith("A2", 12, expect.anything()),
    );
    expect(result.current.selected?.id).toBe("A2");
  });

  it("refetches on identity change and drops stale results", async () => {
    let resolveA: (value: unknown) => void = () => undefined;
    const clientA = fakeClient({
      listMachines: vi.fn().mockReturnValue(new Promise((resolve) => (resolveA = resolve))),
    });
    const clientB = fakeClient({ listMachines: vi.fn().mockResolvedValue([machineB1]) });
    const factory = (identity: Identity) => (identity.tenantId === "company-a" ? clientA : clientB);
    const { result } = renderHook(() => ({ machines: useMachines(), identity: useIdentity() }), {
      wrapper: wrapperFor(factory),
    });
    act(() => result.current.identity.setIdentity("company-b", "user-b-tech"));
    await waitFor(() => expect(result.current.machines.machines.map((m) => m.id)).toEqual(["B1"]));
    await act(async () => resolveA([machineA1, machineA2]));
    expect(result.current.machines.machines.map((m) => m.id)).toEqual(["B1"]);
    expect(result.current.machines.selected?.id).toBe("B1");
  });

  it("reports load errors", async () => {
    const client = fakeClient({
      listMachines: vi.fn().mockRejectedValue(new Error("Could not reach the server.")),
    });
    const { result } = renderHook(() => useMachines(), { wrapper: wrapperFor(() => client) });
    await waitFor(() => expect(result.current.error).toBe("Could not reach the server."));
    expect(result.current.selected).toBeNull();
  });
});
