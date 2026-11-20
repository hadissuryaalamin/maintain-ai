import type { MachineSensors, MachineSummary } from "../api/types";
import { formatMetric } from "./MachineBar";
import { SensorSparkline } from "./SensorSparkline";
import {
  formatMoney,
  formatValue,
  machineTone,
  readingAvailable,
  toneChip,
  toneText,
} from "./status";

function Row({ label, value, className = "text-on-surface" }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex justify-between gap-3 py-1">
      <dt className="text-on-surface-variant">{label}</dt>
      <dd className={`text-right font-semibold ${className}`}>{value}</dd>
    </div>
  );
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }) + " UTC";
}

export function MachinePanel({
  machine,
  sensors,
  onClose,
}: {
  machine: MachineSummary | null;
  sensors: MachineSensors | null;
  onClose?: () => void;
}) {
  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-on-surface">
          <span className="icon text-[18px] text-primary" aria-hidden="true">
            precision_manufacturing
          </span>
          Machine details
        </h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close machine details"
            className="flex h-12 w-12 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container-high"
          >
            <span className="icon text-[22px]" aria-hidden="true">
              close
            </span>
          </button>
        )}
      </div>

      {!machine ? (
        <p className="text-sm text-on-surface-variant">Select a machine to see its status.</p>
      ) : (
        <>
          <section className="rounded-xl border border-outline/40 bg-surface-container">
            <div className="flex items-start justify-between gap-2 border-b border-outline/40 p-4">
              <div className="min-w-0">
                <p className="font-mono text-xs font-bold text-primary">{machine.id}</p>
                <p className="truncate text-sm font-bold text-on-surface">{machine.name}</p>
              </div>
              {machine.active_alarm && (
                <span
                  className={`shrink-0 rounded border px-2 py-0.5 font-mono text-[11px] font-bold ${toneChip[machineTone(machine)]}`}
                >
                  {machine.active_alarm}
                </span>
              )}
            </div>
            <dl className="p-4 font-mono text-xs">
              <Row label="Model" value={machine.model} />
              <Row label="Line" value={machine.line} />
              <Row label="Status" value={machine.status} className={toneText[machineTone(machine)]} />
              {machine.condition && <Row label="Condition" value={machine.condition} />}
              {machine.criticality && <Row label="Criticality" value={machine.criticality} />}
              <Row
                label="Downtime cost"
                value={`${formatMoney(machine.hourly_downtime_cost, machine.cost_currency)}/hr`}
              />
              <Row label="Last status" value={formatTime(machine.last_status_at)} />
            </dl>
          </section>

          <section className="rounded-xl border border-outline/40 bg-surface-container p-4">
            <h3 className="mb-3 text-xs font-bold text-on-surface">Recent sensor readings</h3>
            {!sensors ? (
              <p className="text-xs text-on-surface-variant">Loading readings…</p>
            ) : sensors.series.length === 0 ? (
              <p className="text-xs text-on-surface-variant">No sensor data for this machine.</p>
            ) : (
              <ul className="space-y-3">
                {sensors.series.map((series) => {
                  const latest = series.latest;
                  return (
                    <li key={series.metric} className="rounded-lg bg-surface-container-high p-3">
                      <div className="flex items-baseline justify-between gap-2 font-mono text-xs">
                        <span className="font-semibold text-on-surface">{formatMetric(series.metric)}</span>
                        {readingAvailable(latest) ? (
                          <span className="text-sm font-bold text-on-surface">
                            {formatValue(latest.value)} {series.unit}
                          </span>
                        ) : (
                          <span className="text-on-surface-variant">— {latest?.quality ?? ""}</span>
                        )}
                      </div>
                      <SensorSparkline readings={series.readings} className="mt-2 h-10 w-full" />
                      <p className="mt-1 font-mono text-[10px] text-on-surface-variant">
                        Last {series.readings.length} readings · {formatTime(latest?.recorded_at ?? null)}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          <p className="font-mono text-[10px] text-on-surface-variant">
            Read-only data. Synthetic demo records.
          </p>
        </>
      )}
    </div>
  );
}
