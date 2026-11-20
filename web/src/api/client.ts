import type {
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  DiagnoseRequest,
  DiagnoseResponse,
  MachineSensors,
  MachineSummary,
} from "./types";

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface Identity {
  tenantId: string;
  userId: string;
}

export interface ApiClient {
  listMachines(signal?: AbortSignal): Promise<MachineSummary[]>;
  getMachineSensors(id: string, limit?: number, signal?: AbortSignal): Promise<MachineSensors>;
  diagnose(request: DiagnoseRequest, signal?: AbortSignal): Promise<DiagnoseResponse>;
  decideApproval(
    id: string,
    request: ApprovalDecisionRequest,
    signal?: AbortSignal,
  ): Promise<ApprovalDecisionResponse>;
}

const NETWORK_ERROR = "Could not reach the server.";

export function createApiClient(
  identity: Identity,
  opts: { baseUrl?: string; timeoutMs?: number } = {},
): ApiClient {
  const baseUrl = opts.baseUrl ?? "/api/v1";
  const timeoutMs = opts.timeoutMs ?? 60_000;

  async function request<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), timeoutMs);
    const onCallerAbort = () => timeout.abort();
    signal?.addEventListener("abort", onCallerAbort);
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Tenant-ID": identity.tenantId,
          "X-User-ID": identity.userId,
        },
        signal: timeout.signal,
      });
    } catch {
      // Caller cancellation is not an error to display; timeouts and transport failures are.
      if (signal?.aborted) {
        throw new DOMException("The request was cancelled.", "AbortError");
      }
      throw new ApiError(NETWORK_ERROR, null);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onCallerAbort);
    }

    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail: unknown }).detail
          : null;
      throw new ApiError(
        typeof detail === "string" ? detail : `Request failed (HTTP ${response.status}).`,
        response.status,
      );
    }
    return body as T;
  }

  return {
    listMachines: (signal) => request<MachineSummary[]>("/machines", { method: "GET" }, signal),
    getMachineSensors: (id, limit = 12, signal) =>
      request<MachineSensors>(
        `/machines/${encodeURIComponent(id)}/sensors?limit=${limit}`,
        { method: "GET" },
        signal,
      ),
    diagnose: (body, signal) =>
      request<DiagnoseResponse>(
        "/incidents/diagnose",
        { method: "POST", body: JSON.stringify(body) },
        signal,
      ),
    decideApproval: (id, body, signal) =>
      request<ApprovalDecisionResponse>(
        `/approvals/${encodeURIComponent(id)}/confirm`,
        { method: "POST", body: JSON.stringify(body) },
        signal,
      ),
  };
}
