import { useEffect, type ReactNode } from "react";

/**
 * Responsive frame matching the Stitch screens:
 * - xl (>=1280): sidebar 280 + content + panel 340, all inline
 * - lg (1024-1279): 72px rail + content, panel as right slide-over
 * - below lg: app bar + content, sidebar as left drawer, panel as bottom sheet
 */
export function AppShell({
  sidebar,
  rail,
  header,
  panel,
  children,
  drawerOpen,
  panelOpen,
  onCloseDrawer,
  onClosePanel,
}: {
  sidebar: ReactNode;
  rail: ReactNode;
  header: ReactNode;
  panel: ReactNode;
  children: ReactNode;
  drawerOpen: boolean;
  panelOpen: boolean;
  onCloseDrawer(): void;
  onClosePanel(): void;
}) {
  useEffect(() => {
    if (!drawerOpen && !panelOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      onCloseDrawer();
      onClosePanel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen, panelOpen, onCloseDrawer, onClosePanel]);

  return (
    <div className="flex h-full overflow-hidden bg-surface text-on-surface">
      <aside className="hidden w-[280px] shrink-0 border-r border-outline/40 bg-surface-container-low xl:flex xl:flex-col">
        {sidebar}
      </aside>
      <nav
        aria-label="Navigation rail"
        className="hidden w-[72px] shrink-0 border-r border-outline/40 bg-surface-container-low lg:flex lg:flex-col xl:hidden"
      >
        {rail}
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        {header}
        <div className="relative flex min-h-0 flex-1 flex-col">{children}</div>
      </div>

      <aside className="hidden w-[340px] shrink-0 border-l border-outline/40 bg-surface-container-low xl:block">
        {panel}
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 xl:hidden" role="dialog" aria-modal="true" aria-label="Conversations">
          <button type="button" aria-label="Close conversations" className="absolute inset-0 bg-black/60" onClick={onCloseDrawer} />
          <div className="absolute inset-y-0 left-0 flex w-[min(320px,85vw)] flex-col bg-surface-container-low shadow-2xl">
            {sidebar}
          </div>
        </div>
      )}

      {panelOpen && (
        <div className="fixed inset-0 z-50 xl:hidden" role="dialog" aria-modal="true" aria-label="Machine details">
          <button type="button" aria-label="Close machine details" className="absolute inset-0 bg-black/60" onClick={onClosePanel} />
          <div data-testid="panel-sheet" className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto overscroll-contain rounded-t-2xl bg-surface-container-low shadow-2xl lg:inset-y-0 lg:left-auto lg:right-0 lg:max-h-none lg:w-[360px] lg:rounded-none">
            {panel}
          </div>
        </div>
      )}
    </div>
  );
}
