import { useEffect, useRef, type ReactNode } from "react";
import type { MachineSummary } from "../api/types";
import type { AssistantTurn as AssistantTurnData, Conversation } from "../state/conversations";
import { UserBubble } from "./UserBubble";

export function Thread({
  conversation,
  machine,
  renderAssistant,
}: {
  conversation: Conversation;
  machine: MachineSummary | null;
  renderAssistant(turn: AssistantTurnData): ReactNode;
}) {
  const end = useRef<HTMLDivElement>(null);
  const count = conversation.turns.length;
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [count]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-[860px] flex-col gap-6 px-3 py-6 md:px-6">
        {count === 0 && (
          <div className="mx-auto max-w-md py-10 text-center">
            <p className="text-base font-semibold text-on-surface">
              {machine ? `What's happening with ${machine.id}?` : "Describe the problem"}
            </p>
            <p className="mt-2 text-sm text-on-surface-variant">
              Describe the symptom, alarm code or what you heard. The assistant checks machine status,
              sensor history, manuals and past incidents, then suggests what to check first.
            </p>
          </div>
        )}
        {conversation.turns.map((turn) =>
          turn.role === "user" ? (
            <UserBubble key={turn.id} text={turn.text} at={turn.at} />
          ) : (
            <div key={turn.id}>{renderAssistant(turn)}</div>
          ),
        )}
        <div ref={end} />
      </div>
    </div>
  );
}
