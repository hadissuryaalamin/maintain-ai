import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";
import { diagnoseCompleted } from "../test/fixtures";

function mockFetch(response: { ok?: boolean; status?: number; json?: () => Promise<unknown> }) {
  const fn = vi
    .fn()
    .mockResolvedValue({ ok: true, status: 200, json: async () => ({}), ...response });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

const identity = { tenantId: "company-a", userId: "user-a-tech" };

describe("ApiClient", () => {
  it("sends identity headers", async () => {
    const fetchMock = mockFetch({ json: async () => [] });
    await createApiClient(identity).listMachines();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/machines");
    expect(init.headers["X-Tenant-ID"]).toBe("company-a");
    expect(init.headers["X-User-ID"]).toBe("user-a-tech");
  });

  it("diagnose posts JSON to /api/v1/incidents/diagnose", async () => {
    const fetchMock = mockFetch({ json: async () => diagnoseCompleted });
    const result = await createApiClient(identity).diagnose({ message: "Pump noise on A2" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/incidents/diagnose");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ message: "Pump noise on A2" });
    expect(result.run_id).toBe(diagnoseCompleted.run_id);
  });

  it("getMachineSensors passes limit query", async () => {
    const fetchMock = mockFetch({ json: async () => ({ machine_id: "A2", series: [] }) });
    await createApiClient(identity).getMachineSensors("A2", 5);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/v1/machines/A2/sensors?limit=5");
  });

  it("decideApproval posts the decision", async () => {
    const fetchMock = mockFetch({
      json: async () => ({ approval_id: "x", status: "approved", result: null }),
    });
    await createApiClient(identity).decideApproval("x", {
      approved: true,
      idempotency_key: "key-12345",
    });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/approvals/x/confirm");
    expect(JSON.parse(init.body)).toEqual({ approved: true, idempotency_key: "key-12345" });
  });

  it("maps 404 detail to ApiError", async () => {
    mockFetch({ ok: false, status: 404, json: async () => ({ detail: "Machine not found." }) });
    const error = await createApiClient(identity)
      .getMachineSensors("Z9")
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Machine not found.");
    expect((error as ApiError).status).toBe(404);
  });

  it("falls back to a generic message when detail is not a string", async () => {
    mockFetch({ ok: false, status: 422, json: async () => ({ detail: [{ msg: "bad" }] }) });
    const error = (await createApiClient(identity)
      .listMachines()
      .catch((e: unknown) => e)) as ApiError;
    expect(error.message).toBe("Request failed (HTTP 422).");
  });

  it("maps network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = (await createApiClient(identity)
      .listMachines()
      .catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("Could not reach the server.");
    expect(error.status).toBeNull();
  });

  it("propagates caller aborts as AbortError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    const controller = new AbortController();
    controller.abort();
    const error = (await createApiClient(identity)
      .listMachines(controller.signal)
      .catch((e: unknown) => e)) as Error;
    expect(error.name).toBe("AbortError");
  });
});
