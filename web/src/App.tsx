import { useCallback, useState } from "react";
import { AppShell } from "./components/AppShell";
import { IdentityPicker } from "./components/IdentityPicker";
import { MachineBar } from "./components/MachineBar";
import { MachinePanel } from "./components/MachinePanel";
import { useMachines } from "./hooks/useMachines";
import { IdentityProvider } from "./state/identity";

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded border border-primary/40 bg-primary/10 text-primary">
        <span className="icon text-[22px]" aria-hidden="true">
          settings
        </span>
      </div>
      {!compact && (
        <span className="text-sm font-bold uppercase tracking-wide text-on-surface">Maintain AI</span>
      )}
    </div>
  );
}

function Workspace() {
  const machines = useMachines();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
  const closePanel = useCallback(() => setPanelOpen(false), []);

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center border-b border-outline/30 px-4">
        <Brand />
      </div>
      <div className="flex-1" />
      <div className="border-t border-outline/30 p-3">
        <IdentityPicker />
      </div>
    </div>
  );

  const rail = (
    <div className="flex h-full flex-col items-center gap-2 py-3">
      <Brand compact />
      <div className="flex-1" />
      <IdentityPicker compact />
    </div>
  );

  const menuButton = (
    <button
      type="button"
      aria-label="Open conversations"
      onClick={() => setDrawerOpen(true)}
      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg text-on-surface hover:bg-surface-container lg:hidden"
    >
      <span className="icon text-[26px]" aria-hidden="true">
        menu
      </span>
    </button>
  );

  return (
    <AppShell
      sidebar={sidebar}
      rail={rail}
      header={
        <MachineBar
          machine={machines.selected}
          sensors={machines.sensors}
          onOpenDetails={() => setPanelOpen(true)}
          leading={menuButton}
        />
      }
      panel={<MachinePanel machine={machines.selected} sensors={machines.sensors} onClose={panelOpen ? closePanel : undefined} />}
      drawerOpen={drawerOpen}
      panelOpen={panelOpen}
      onCloseDrawer={closeDrawer}
      onClosePanel={closePanel}
    >
      <div className="flex flex-1 items-center justify-center p-6 text-sm text-on-surface-variant">
        {machines.error ?? (machines.loading ? "Loading machines…" : "Conversation coming soon")}
      </div>
    </AppShell>
  );
}

export default function App() {
  return (
    <IdentityProvider>
      <Workspace />
    </IdentityProvider>
  );
}
