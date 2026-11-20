import type { MachineSummary, PendingApproval } from "../api/types";
import { hasAnswer, type AssistantTurn as AssistantTurnData } from "../state/conversations";
import {
  ActionSteps,
  DiagnosisCard,
  EvidenceList,
  MissingInfo,
  SafetyBanner,
  ToolTrace,
} from "./diagnosis";
import { formatMoney } from "./status";

export const STATUS_COPY = "Read-only access · cannot control equipment";

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function Header({ at }: { at: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded bg-primary/20 text-primary">
          <span className="icon text-[20px]" aria-hidden="true">
            smart_toy
          </span>
        </div>
        <div>
          <p className="text-sm font-bold text-on-surface">Maintain AI</p>
          <p className="flex items-center gap-1.5 text-[11px] text-on-surface-variant">
            <span className="h-1.5 w-1.5 rounded-full bg-status-normal" aria-hidden="true" />
            {STATUS_COPY}
          </p>
        </div>
      </div>
      <time className="font-mono text-[11px] text-on-surface-variant" dateTime={at}>
        {time(at)}
      </time>
    </div>
  );
}

function RunLink({ runId }: { runId: string }) {
  const dashboard = import.meta.env.VITE_DASHBOARD_URL as string | undefined;
  const label = `Run ${runId.slice(0, 8)}`;
  if (dashboard) {
    return (
      <a
        href={`${dashboard}?run_id=${encodeURIComponent(runId)}`}
        target="_blank"
        rel="noreferrer"
        className="inline-flex min-h-12 items-center px-2 font-mono text-[10px] text-on-surface-variant underline hover:text-primary"
      >
        {label}
      </a>
    );
  }
  return (
    <button
      type="button"
      title="Copy run id"
      onClick={() => void navigator.clipboard?.writeText(runId).catch(() => undefined)}
      className="inline-flex min-h-12 items-center px-2 font-mono text-[10px] text-on-surface-variant underline hover:text-primary"
    >
      {label}
    </button>
  );
}

function ErrorBody({ message, runId, onRetry }: { message: string; runId?: string; onRetry(): void }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-xl border border-status-critical/30 bg-status-critical/10 p-4">
      <p className="text-sm text-on-surface">{message}</p>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="h-12 rounded-lg bg-surface-container-high px-4 text-sm font-semibold text-on-surface hover:bg-surface-container"
        >
          Retry
        </button>
        {runId && <RunLink runId={runId} />}
      </div>
    </div>
  );
}

function PendingApprovalNotice({ approval }: { approval: PendingApproval }) {
  return (
    <div className="rounded-xl border border-outline/40 bg-surface-container p-4">
      <p className="text-sm text-on-surface">{approval.message}</p>
    </div>
  );
}

export function AssistantTurn({
  turn,
  machine,
  onDraftWorkOrder,
  onRetry,
  onFollowUp,
  busy = false,
  renderApproval = (approval) => <PendingApprovalNotice approval={approval} />,
}: {
  turn: AssistantTurnData;
  machine: MachineSummary | null;
  onDraftWorkOrder(): void;
  onRetry(): void;
  onFollowUp(): void;
  busy?: boolean;
  renderApproval?: (approval: PendingApproval) => React.ReactNode;
}) {
  if (turn.state === "pending") {
    return (
      <article className="flex flex-col gap-4">
        <Header at={turn.at} />
        <p className="flex items-center gap-2 text-sm text-on-surface-variant" aria-live="polite">
          <span className="icon animate-spin text-[18px] text-primary" aria-hidden="true">
            progress_activity
          </span>
          Checking machine data…
        </p>
      </article>
    );
  }

  if (turn.state === "error") {
    return (
      <article className="flex flex-col gap-4">
        <Header at={turn.at} />
        <ErrorBody message={turn.message} onRetry={onRetry} />
      </article>
    );
  }

  const { response } = turn;
  const diagnostic = response.diagnostic;
  return (
    <article className="flex flex-col gap-4">
      <Header at={turn.at} />
      <ToolTrace items={response.tool_trace} />

      {!hasAnswer(response) && (
        <ErrorBody
          message={response.error ?? `The assistant could not finish (${response.status}).`}
          runId={response.run_id}
          onRetry={onRetry}
        />
      )}

      {diagnostic && (
        <div className="flex flex-col gap-5 rounded-xl border border-outline/40 bg-surface-container p-4 md:p-5">
          <DiagnosisCard diagnostic={diagnostic} />
          <EvidenceList observations={diagnostic.observations} />
          <ActionSteps actions={diagnostic.recommended_actions} />
          <MissingInfo items={diagnostic.missing_information} />
          <SafetyBanner notice={diagnostic.safety_notice} />
          <div className="flex flex-col gap-3 pt-1 md:flex-row md:items-center md:justify-between">
            {machine && (
              <span className="inline-flex items-center gap-2 self-start rounded-full bg-surface-container-high px-3 py-1.5 font-mono text-xs font-bold text-on-surface">
                <span className="icon text-[16px] text-status-warning" aria-hidden="true">
                  payments
                </span>
                {`~${formatMoney(machine.hourly_downtime_cost, machine.cost_currency)}/hr if stopped${
                  machine.criticality ? ` · ${machine.criticality} criticality` : ""
                }`}
              </span>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={onDraftWorkOrder}
                disabled={busy}
                className="flex h-12 items-center justify-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-bold text-on-primary hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="icon text-[18px]" aria-hidden="true">
                  assignment_add
                </span>
                Draft work order
              </button>
              <button
                type="button"
                onClick={onFollowUp}
                className="flex h-12 items-center justify-center gap-1.5 rounded-lg bg-surface-container-high px-4 text-sm font-medium text-on-surface hover:bg-surface-container-low"
              >
                <span className="icon text-[18px]" aria-hidden="true">
                  chat
                </span>
                Ask follow-up
              </button>
            </div>
          </div>
        </div>
      )}

      {response.pending_approval && renderApproval(response.pending_approval)}

      {hasAnswer(response) && (
        <div className="flex justify-end">
          <RunLink runId={response.run_id} />
        </div>
      )}
    </article>
  );
}
