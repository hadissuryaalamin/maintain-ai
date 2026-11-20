import { useId, useState } from "react";
import type {
  Confidence,
  DiagnosticResult,
  Observation,
  PossibleCause,
  RecommendedAction,
  SourceType,
  ToolTraceItem,
} from "../api/types";

const CONFIDENCE_BARS: Record<Confidence, number> = { low: 1, medium: 3, high: 5 };
const CONFIDENCE_LABEL: Record<Confidence, string> = {
  low: "Low confidence",
  medium: "Medium confidence",
  high: "High confidence",
};

export function ConfidenceBars({ confidence }: { confidence: Confidence }) {
  const filled = CONFIDENCE_BARS[confidence] ?? 0;
  return (
    <span className="inline-flex items-center gap-2 rounded-lg bg-surface-container-high px-2.5 py-1">
      <span className="flex h-3.5 items-center gap-0.5" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => (
          <span key={index} className={`h-3.5 w-1.5 rounded-sm ${index < filled ? "bg-primary" : "bg-outline"}`} />
        ))}
      </span>
      <span className="font-mono text-[11px] font-bold text-primary">{CONFIDENCE_LABEL[confidence] ?? confidence}</span>
    </span>
  );
}

function Section({
  title,
  icon,
  children,
  className = "",
}: {
  title: string;
  icon?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={className}>
      <h3
        id={id}
        className="mb-2 flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-wider text-on-surface-variant"
      >
        {icon && (
          <span className="icon text-[15px]" aria-hidden="true">
            {icon}
          </span>
        )}
        {title}
      </h3>
      {children}
    </section>
  );
}

const TOOL_OK = new Set(["succeeded", "success", "ok", "completed"]);

export function ToolTrace({ items }: { items: ToolTraceItem[] }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (items.length === 0) return null;
  const total = items.reduce((sum, item) => sum + item.latency_ms, 0);
  return (
    <div className="rounded-lg border border-outline/40 bg-surface-container-low">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-12 w-full items-center justify-between gap-2 px-3 text-left"
      >
        <span className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wide text-on-surface">
          <span className="icon text-[16px] text-primary" aria-hidden="true">
            terminal
          </span>
          Used {items.length} {items.length === 1 ? "tool" : "tools"}
          <span className="font-normal normal-case text-on-surface-variant">({total} ms)</span>
        </span>
        <span className="icon text-[18px] text-on-surface-variant" aria-hidden="true">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && (
        <ul id={panelId} className="grid grid-cols-1 gap-2 px-3 pb-3 sm:grid-cols-2">
          {items.map((item) => {
            const ok = TOOL_OK.has(item.status.toLowerCase());
            return (
              <li key={item.call_id} className="flex flex-col gap-1 rounded bg-surface-container p-2">
                <span className="flex items-center justify-between">
                  <span
                    className={`icon text-[14px] ${ok ? "text-status-normal" : "text-status-warning"}`}
                    aria-label={ok ? "Succeeded" : `Status ${item.status}`}
                  >
                    {ok ? "check_circle" : "error"}
                  </span>
                  <span className="font-mono text-[10px] text-on-surface-variant">{item.latency_ms} ms</span>
                </span>
                <span className="truncate font-mono text-[11px] font-medium text-on-surface">{item.tool_name}</span>
                {item.error_category && (
                  <span className="font-mono text-[10px] text-status-warning">{item.error_category}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function DiagnosisCard({ diagnostic }: { diagnostic: DiagnosticResult }) {
  const [likely, ...alternatives] = diagnostic.possible_causes;
  return (
    <div className="space-y-4">
      <div>
        <span className="block font-mono text-[10px] font-bold uppercase tracking-widest text-primary">
          Preliminary diagnosis
        </span>
        <p className="mt-1 text-sm leading-relaxed text-on-surface">{diagnostic.incident_summary}</p>
      </div>
      {likely && <LikelyCause cause={likely} />}
      {alternatives.length > 0 && (
        <Section title="Alternatives">
          <ul className="space-y-2">
            {alternatives.map((cause, index) => (
              <li key={`${cause.cause}-${index}`} className="rounded-lg bg-surface-container-high p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-on-surface">{cause.cause}</span>
                  <ConfidenceBars confidence={cause.confidence} />
                </div>
                <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">{cause.reasoning_summary}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function LikelyCause({ cause }: { cause: PossibleCause }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="rounded-lg border border-primary/25 bg-primary/10 p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="icon mt-0.5 text-[20px] text-primary" aria-hidden="true">
            report_problem
          </span>
          <div className="min-w-0">
            <h3 id={id} className="font-mono text-[10px] font-bold uppercase tracking-widest text-primary">
              Likely cause
            </h3>
            <p className="text-sm font-bold text-on-surface">{cause.cause}</p>
          </div>
        </div>
        <ConfidenceBars confidence={cause.confidence} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-on-surface/90">{cause.reasoning_summary}</p>
    </section>
  );
}

const SOURCE_ICON: Record<SourceType, string> = {
  manual: "menu_book",
  incident_history: "history",
  tool: "sensors",
  user: "person",
};
const SOURCE_LABEL: Record<SourceType, string> = {
  manual: "Manual",
  incident_history: "Past incident",
  tool: "Machine data",
  user: "Your report",
};

export function EvidenceList({ observations }: { observations: Observation[] }) {
  if (observations.length === 0) return null;
  return (
    <Section title="Evidence" icon="verified">
      <ul className="no-scrollbar -mx-1 flex snap-x snap-mandatory gap-3 overflow-x-auto px-1 pb-1 md:mx-0 md:grid md:grid-cols-3 md:overflow-visible md:px-0">
        {observations.map((observation, index) => (
          <li
            key={`${observation.source_reference}-${index}`}
            className="flex w-[260px] shrink-0 snap-start flex-col justify-between gap-2 rounded-lg bg-surface-container-high p-3 md:w-auto"
          >
            <div>
              <span className="mb-1 flex items-center gap-1.5 text-xs font-bold text-primary">
                <span className="icon text-[16px]" aria-hidden="true">
                  {SOURCE_ICON[observation.source_type] ?? "description"}
                </span>
                {SOURCE_LABEL[observation.source_type] ?? observation.source_type}
              </span>
              <blockquote className="text-[12px] leading-snug text-on-surface-variant">
                “{observation.statement}”
              </blockquote>
            </div>
            <span className="break-all font-mono text-[10px] text-on-surface-variant">
              {observation.source_reference}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function ActionSteps({ actions }: { actions: RecommendedAction[] }) {
  if (actions.length === 0) return null;
  const ordered = [...actions].sort((a, b) => a.step - b.step);
  return (
    <Section title="Recommended checks">
      <ol className="space-y-2">
        {ordered.map((action) => (
          <li key={action.step} className="flex min-h-14 items-start gap-3 rounded-lg bg-surface-container-high p-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-surface font-mono text-xs font-bold text-primary">
              {String(action.step).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-on-surface">{action.action}</p>
              {(action.requires_shutdown || action.requires_approval) && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {action.requires_shutdown && (
                    <span className="rounded border border-status-critical/40 bg-status-critical/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-status-critical">
                      Requires shutdown
                    </span>
                  )}
                  {action.requires_approval && (
                    <span className="rounded border border-status-warning/40 bg-status-warning/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-status-warning">
                      Requires approval
                    </span>
                  )}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

export function MissingInfo({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Section title="Missing information" icon="help">
      <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-on-surface-variant">
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
      </ul>
    </Section>
  );
}

export function SafetyBanner({ notice }: { notice: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-outline/40 bg-surface-container-high p-3.5">
      <span className="icon mt-0.5 shrink-0 text-[24px] text-primary" aria-hidden="true">
        warning
      </span>
      <div>
        <p className="font-mono text-[11px] font-bold uppercase tracking-wide text-primary">Safety</p>
        <p className="mt-0.5 text-xs leading-snug text-on-surface">{notice}</p>
      </div>
    </div>
  );
}
