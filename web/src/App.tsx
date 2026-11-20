import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "./components/AppShell";
import { AssistantTurn } from "./components/AssistantTurn";
import { Composer, type ComposerHandle } from "./components/Composer";
import { ConversationList } from "./components/ConversationList";
import { IdentityPicker } from "./components/IdentityPicker";
import { MachineBar } from "./components/MachineBar";
import { MachinePanel } from "./components/MachinePanel";
import { Thread } from "./components/Thread";
import { useMachines, type MachinesState } from "./hooks/useMachines";
import { ConversationProvider, useConversation } from "./state/ConversationProvider";
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

function RailButton({ icon, label, onClick }: { icon: string; label: string; onClick(): void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex h-12 w-12 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
    >
      <span className="icon text-[24px]" aria-hidden="true">
        {icon}
      </span>
    </button>
  );
}

function Workspace({ machines }: { machines: MachinesState }) {
  const conversation = useConversation();
  const composer = useRef<ComposerHandle>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
  const closePanel = useCallback(() => setPanelOpen(false), []);
  const { select: selectMachine, machines: machineList } = machines;

  // Opening a saved conversation brings back the machine it was about.
  const activeMachine = conversation.active.machineId;
  useEffect(() => {
    if (activeMachine && machineList.some((machine) => machine.id === activeMachine)) {
      selectMachine(activeMachine);
    }
  }, [activeMachine, machineList, selectMachine]);

  const startNew = () => {
    conversation.newConversation();
    setDrawerOpen(false);
  };

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center border-b border-outline/30 px-4">
        <Brand />
      </div>
      <ConversationList
        list={conversation.list}
        activeId={conversation.active.id}
        onSelect={(id) => {
          conversation.select(id);
          setDrawerOpen(false);
        }}
        onNew={startNew}
      />
      <div className="shrink-0 border-t border-outline/30 p-3">
        <IdentityPicker />
      </div>
    </div>
  );

  const rail = (
    <div className="flex h-full flex-col items-center gap-2 py-3">
      <Brand compact />
      <div className="mt-2 flex flex-col gap-1">
        <RailButton icon="add" label="New conversation" onClick={startNew} />
        <RailButton icon="history" label="Conversations" onClick={() => setDrawerOpen(true)} />
      </div>
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
      panel={
        <MachinePanel
          machine={machines.selected}
          sensors={machines.sensors}
          onClose={panelOpen ? closePanel : undefined}
        />
      }
      drawerOpen={drawerOpen}
      panelOpen={panelOpen}
      onCloseDrawer={closeDrawer}
      onClosePanel={closePanel}
    >
      {machines.error && (
        <div role="alert" className="flex items-center justify-between gap-3 bg-status-critical/10 px-4 py-2 text-xs text-status-critical">
          <span>{machines.error}</span>
          <button type="button" onClick={machines.reload} className="h-9 rounded px-3 font-bold underline">
            Retry
          </button>
        </div>
      )}
      <Thread
        conversation={conversation.active}
        machine={machines.selected}
        renderAssistant={(turn) => (
          <AssistantTurn
            turn={turn}
            machine={machines.selected}
            onRetry={() => void conversation.retry(turn.id)}
            onDraftWorkOrder={() => {
              const id = machines.selected?.id ?? conversation.active.machineId;
              void conversation.send(
                `Please propose a draft work order for machine ${id ?? "this machine"} based on this diagnosis.`,
              );
            }}
            onFollowUp={() => composer.current?.focus()}
          />
        )}
      />
      <Composer
        ref={composer}
        onSend={(text) => void conversation.send(text)}
        sending={conversation.sending}
        machines={machines.machines}
        selected={machines.selected}
        onSelectMachine={machines.select}
      />
    </AppShell>
  );
}

function ConversationScope() {
  const machines = useMachines();
  return (
    <ConversationProvider machineId={machines.selected?.id ?? null}>
      <Workspace machines={machines} />
    </ConversationProvider>
  );
}

export default function App() {
  return (
    <IdentityProvider>
      <ConversationScope />
    </IdentityProvider>
  );
}
