import type { MachineSummary } from "../api/types";
import { machineTone, toneDot } from "./status";

/** Compact machine chip with a native select overlay (large, glove-friendly hit area). */
export function MachineSelector({
  machines,
  selected,
  onSelect,
}: {
  machines: MachineSummary[];
  selected: MachineSummary | null;
  onSelect(id: string): void;
}) {
  return (
    <label className="relative inline-flex min-h-9 items-center gap-1.5 rounded bg-primary/15 px-2 font-mono text-[11px] font-bold text-primary">
      {selected && <span className={`h-1.5 w-1.5 rounded-full ${toneDot[machineTone(selected)]}`} aria-hidden="true" />}
      <span>{selected ? selected.id : "No machine"}</span>
      <span className="icon text-[14px]" aria-hidden="true">
        expand_more
      </span>
      <select
        aria-label="Machine"
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        value={selected?.id ?? ""}
        disabled={machines.length === 0}
        onChange={(event) => onSelect(event.target.value)}
      >
        {machines.map((machine) => (
          <option key={machine.id} value={machine.id}>
            {machine.id} · {machine.name}
          </option>
        ))}
      </select>
    </label>
  );
}
