import type { MachineSummary, SensorPointOut } from "../api/types";

export type Tone = "critical" | "warning" | "normal" | "muted";

export function machineTone(machine: MachineSummary): Tone {
  const condition = (machine.condition ?? "").toLowerCase();
  const status = machine.status.toLowerCase();
  if (status === "stopped" || condition === "critical") return "critical";
  if (condition === "warning" || machine.active_alarm) return "warning";
  return "normal";
}

export const toneText: Record<Tone, string> = {
  critical: "text-status-critical",
  warning: "text-status-warning",
  normal: "text-status-normal",
  muted: "text-on-surface-variant",
};

export const toneDot: Record<Tone, string> = {
  critical: "bg-status-critical",
  warning: "bg-status-warning",
  normal: "bg-status-normal",
  muted: "bg-outline",
};

export const toneChip: Record<Tone, string> = {
  critical: "bg-status-critical/15 text-status-critical border-status-critical/40",
  warning: "bg-status-warning/15 text-status-warning border-status-warning/40",
  normal: "bg-status-normal/10 text-status-normal border-status-normal/30",
  muted: "bg-surface-container text-on-surface-variant border-outline",
};

export function readingAvailable(point: SensorPointOut | null): point is SensorPointOut & { value: number } {
  return point !== null && point.value !== null && point.quality === "good";
}

export function formatValue(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(Math.abs(value) < 10 ? 1 : 0);
}

export function formatMoney(amount: string | number, currency: string | null): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) return String(amount);
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency ?? "USD",
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toFixed(0)} ${currency ?? ""}`.trim();
  }
}
