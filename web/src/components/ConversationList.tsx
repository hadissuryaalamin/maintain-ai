import type { Conversation } from "../state/conversations";

function dayLabel(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return date.getTime() >= startOfToday ? "Today" : "Earlier";
}

export function ConversationList({
  list,
  activeId,
  onSelect,
  onNew,
}: {
  list: Conversation[];
  activeId: string;
  onSelect(id: string): void;
  onNew(): void;
}) {
  const saved = list.filter((conversation) => conversation.turns.length > 0);
  const groups = new Map<string, Conversation[]>();
  for (const conversation of saved) {
    const label = dayLabel(conversation.updatedAt);
    groups.set(label, [...(groups.get(label) ?? []), conversation]);
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-primary text-sm font-bold text-on-primary hover:bg-primary/90"
        >
          <span className="icon text-[20px]" aria-hidden="true">
            add
          </span>
          New conversation
        </button>
      </div>
      <nav aria-label="Conversations" className="min-h-0 flex-1 space-y-4 overflow-y-auto px-2 pb-3">
        {saved.length === 0 && (
          <p className="px-3 text-xs text-on-surface-variant">Your conversations appear here.</p>
        )}
        {[...groups.entries()].map(([label, items]) => (
          <div key={label} className="space-y-1">
            <h3 className="px-2 py-1 font-mono text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">
              {label}
            </h3>
            {items.map((conversation) => {
              const active = conversation.id === activeId;
              return (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => onSelect(conversation.id)}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-12 w-full flex-col gap-0.5 rounded-lg px-3 py-2 text-left ${
                    active
                      ? "border-l-2 border-primary bg-surface-container"
                      : "hover:bg-surface-container/60"
                  }`}
                >
                  {conversation.machineId && (
                    <span className={`font-mono text-xs font-semibold ${active ? "text-primary" : "text-on-surface-variant"}`}>
                      {conversation.machineId}
                    </span>
                  )}
                  <span className="truncate text-xs font-medium text-on-surface">{conversation.title}</span>
                  <span className="font-mono text-[10px] text-on-surface-variant">
                    {new Date(conversation.updatedAt).toLocaleTimeString("en-GB", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </div>
  );
}
