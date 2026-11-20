import { useCallback, useEffect, useMemo, useState } from "react";
import type { MachineSensors, MachineSummary } from "../api/types";
import { useIdentity } from "../state/identity";

export const SENSOR_LIMIT = 12;

export interface MachinesState {
  machines: MachineSummary[];
  selected: MachineSummary | null;
  select(id: string): void;
  sensors: MachineSensors | null;
  loading: boolean;
  error: string | null;
  reload(): void;
}

function messageOf(error: unknown): string | null {
  if (error instanceof Error && error.name === "AbortError") return null;
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function useMachines(): MachinesState {
  const { client } = useIdentity();
  const [machines, setMachines] = useState<MachineSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sensors, setSensors] = useState<MachineSensors | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Machine list follows the identity (client is recreated per identity).
  useEffect(() => {
    const controller = new AbortController();
    setMachines([]);
    setSelectedId(null);
    setSensors(null);
    setLoading(true);
    setError(null);
    client
      .listMachines(controller.signal)
      .then((list) => {
        if (controller.signal.aborted) return;
        setMachines(list);
        setSelectedId(list[0]?.id ?? null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(messageOf(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [client, reloadToken]);

  // Sensors follow the selected machine.
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setSensors(null);
    client
      .getMachineSensors(selectedId, SENSOR_LIMIT, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setSensors(value);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(messageOf(err));
      });
    return () => controller.abort();
  }, [client, selectedId, reloadToken]);

  const selected = useMemo(
    () => machines.find((machine) => machine.id === selectedId) ?? null,
    [machines, selectedId],
  );
  const select = useCallback((id: string) => setSelectedId(id), []);
  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  return { machines, selected, select, sensors, loading, error, reload };
}
