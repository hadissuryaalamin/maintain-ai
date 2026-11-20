import type { MachineSummary } from "../api/types";
import type { AssistantTurn as AssistantTurnData } from "../state/conversations";

// Minimal renderer; full diagnostic rendering lands in the next task.
export function AssistantTurn({
  turn,
  onRetry,
}: {
  turn: AssistantTurnData;
  machine: MachineSummary | null;
  onDraftWorkOrder(): void;
  onRetry(): void;
  onFollowUp(): void;
}) {
  if (turn.state === "pending") return <p className="text-sm text-on-surface-variant">Checking machine data…</p>;
  if (turn.state === "error")
    return (
      <div role="alert" className="text-sm text-status-critical">
        {turn.message}{" "}
        <button type="button" onClick={onRetry} className="underline">
          Retry
        </button>
      </div>
    );
  return <p className="text-sm">{turn.response.diagnostic?.incident_summary ?? turn.response.error}</p>;
}
