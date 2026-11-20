import type { MachineSensors, MachineSummary, SensorSeries } from "../api/types";
import { formatValue, machineTone, readingAvailable, toneChip, toneDot } from "./status";

export function formatMetric(metric: string): string {
  const words = metric.split("_").filter(Boolean);
  return words
    .map((word, index) => {
      if (word === "rms") return "RMS";
      return index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word;
    })
    .join(" ");
}

export function Reading({ series, compact = false }: { series: SensorSeries; compact?: boolean }) {
  const latest = series.latest;
  const available = readingAvailable(latest);
  return (
    <div
      className={`flex shrink-0 flex-col rounded-lg border border-outline/40 bg-surface-container px-3 ${
        compact ? "py-1" : "py-2"
      }`}
    >
      <span className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
        {formatMetric(series.metric)}
      </span>
      {available ? (
        <span className="font-mono text-sm font-bold text-on-surface">
          {`${formatValue(latest.value)} ${series.unit}`}
        </span>
      ) : (
        <span className="flex items-baseline gap-1.5 font-mono text-sm">
          <span className="font-bold text-on-surface-variant">—</span>
          {latest && <span className="text-[10px] text-on-surface-variant">{latest.quality}</span>}
        </span>
      )}
    </div>
  );
}

export function MachineBar({
  machine,
  sensors,
  onOpenDetails,
  leading,
}: {
  machine: MachineSummary | null;
  sensors: MachineSensors | null;
  onOpenDetails(): void;
  leading?: React.ReactNode;
}) {
  if (!machine) {
    return (
      <header className="flex h-16 items-center gap-2 border-b border-outline/40 bg-surface-container-low px-3">
        {leading}
        <span className="text-sm text-on-surface-variant">No machine selected</span>
      </header>
    );
  }
  const tone = machineTone(machine);
  return (
    <header className="border-b border-outline/40 bg-surface-container-low">
      <div className="flex min-h-16 items-center gap-2 px-3 py-2">
        {leading}
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${toneDot[tone]}`} aria-hidden="true" />
            <span className="font-mono text-sm font-bold text-primary">{machine.id}</span>
            <span className="truncate text-sm font-medium text-on-surface">{machine.name}</span>
          </div>
          {machine.active_alarm && (
            <span
              className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-xs font-bold ${toneChip[tone]}`}
            >
              <span className="icon text-[14px]" aria-hidden="true">
                warning
              </span>
              {machine.active_alarm}
            </span>
          )}
          <span className="hidden font-mono text-[11px] text-on-surface-variant lg:inline">
            {machine.model} · {machine.line} · {machine.status}
          </span>
        </div>
        <button
          type="button"
          onClick={onOpenDetails}
          className="flex h-12 shrink-0 items-center gap-1.5 rounded-lg border border-primary/40 bg-primary-container px-3 text-xs font-bold text-on-primary-container xl:hidden"
        >
          <span className="icon text-[18px]" aria-hidden="true">
            info
          </span>
          <span className="hidden md:inline">Machine details</span>
        </button>
      </div>
      {sensors && sensors.series.length > 0 && (
        <div className="no-scrollbar flex gap-2 overflow-x-auto px-3 pb-2 md:grid md:grid-cols-3 md:overflow-visible lg:flex">
          {sensors.series.map((series) => (
            <Reading key={series.metric} series={series} compact />
          ))}
        </div>
      )}
    </header>
  );
}
