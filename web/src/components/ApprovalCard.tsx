import { useRef, useState } from "react";
import { ApiError, type ApiClient } from "../api/client";
import type { ApprovalDecisionResponse, PendingApproval } from "../api/types";
import { newId } from "../state/conversations";

export const APPROVAL_FOOTER = "Creates a draft only. No equipment action is taken.";

const FIELDS: ReadonlyArray<[key: string, label: string]> = [
  ["machine_id", "Machine"],
  ["title", "Title"],
  ["description", "Description"],
  ["priority", "Priority"],
];

type Phase =
  | { kind: "idle" }
  | { kind: "submitting"; approved: boolean }
  | { kind: "approved"; result: ApprovalDecisionResponse }
  | { kind: "rejected" }
  | { kind: "error"; message: string };

function workOrderId(response: ApprovalDecisionResponse): string | null {
  const value = response.result?.["work_order_id"];
  return typeof value === "string" ? value : null;
}

export function ApprovalCard({ approval, client }: { approval: PendingApproval; client: ApiClient }) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const idempotencyKey = useRef(newId());
  const busy = useRef(false);

  async function decide(approved: boolean) {
    if (busy.current) return;
    busy.current = true;
    setPhase({ kind: "submitting", approved });
    try {
      const result = await client.decideApproval(approval.approval_id, {
        approved,
        idempotency_key: idempotencyKey.current,
      });
      // Trust the server outcome over the button pressed (e.g. an already-decided approval).
      setPhase(approved && result.status !== "rejected" ? { kind: "approved", result } : { kind: "rejected" });
    } catch (error) {
      setPhase({
        kind: "error",
        message: error instanceof ApiError ? error.message : "The decision could not be saved. Try again.",
      });
      busy.current = false;
    }
  }

  const fields = FIELDS.flatMap(([key, label]) => {
    const value = approval.proposed_action[key];
    return value === undefined || value === null || value === "" ? [] : [[label, String(value)] as const];
  });
  const decided = phase.kind === "approved" || phase.kind === "rejected";
  const submitting = phase.kind === "submitting";

  return (
    <section aria-label="Draft work order approval" className="rounded-xl border border-outline/40 bg-surface-container p-4 md:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-on-surface">
          <span className="icon text-[20px] text-primary" aria-hidden="true">
            assignment
          </span>
          {decided ? "Draft work order" : "Draft work order — needs your approval"}
        </h3>
        <span
          className={`rounded border px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${
            phase.kind === "approved"
              ? "border-status-normal/40 bg-status-normal/10 text-status-normal"
              : phase.kind === "rejected"
                ? "border-outline bg-surface-container-high text-on-surface-variant"
                : "border-status-warning/40 bg-status-warning/15 text-status-warning"
          }`}
        >
          {phase.kind === "approved" ? "Draft created" : phase.kind === "rejected" ? "Rejected" : "Awaiting approval"}
        </span>
      </div>

      <p className="mb-3 text-sm text-on-surface">{approval.message}</p>

      {fields.length > 0 && (
        <dl className="mb-4 grid grid-cols-1 gap-3 rounded-lg bg-surface-container-high p-4 text-xs md:grid-cols-2">
          {fields.map(([label, value]) => (
            <div key={label} className={label === "Description" ? "md:col-span-2" : undefined}>
              <dt className="font-mono text-[10px] uppercase text-on-surface-variant">{label}</dt>
              <dd className={`font-semibold text-on-surface ${label === "Description" ? "" : "font-mono"}`}>{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {phase.kind === "approved" && workOrderId(phase.result) && (
        <p className="mb-3 text-sm text-on-surface">
          Work order <span className="font-mono font-bold text-primary">{workOrderId(phase.result)}</span>
        </p>
      )}

      {phase.kind === "error" && (
        <p role="alert" className="mb-3 text-sm text-status-critical">
          {phase.message}
        </p>
      )}

      {!decided && (
        <div className="flex flex-col gap-2 md:flex-row">
          <button
            type="button"
            disabled={submitting}
            onClick={() => void decide(true)}
            className="flex h-14 flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-6 text-sm font-bold text-on-primary hover:bg-primary/90 disabled:opacity-50"
          >
            <span className="icon text-[20px]" aria-hidden="true">
              check_circle
            </span>
            Approve &amp; create draft
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void decide(false)}
            className="flex h-14 items-center justify-center rounded-lg bg-surface-container-high px-6 text-sm font-semibold text-on-surface hover:text-status-critical disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}

      <p className="mt-3 font-mono text-[10px] text-on-surface-variant">{APPROVAL_FOOTER}</p>
    </section>
  );
}
