import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("bottom sheet scrolls its own content", () => {
    render(
      <AppShell
        sidebar={<div />}
        rail={<div />}
        header={<div />}
        panel={<div>panel body</div>}
        drawerOpen={false}
        panelOpen
        onCloseDrawer={() => undefined}
        onClosePanel={() => undefined}
      >
        <div />
      </AppShell>,
    );
    const sheet = screen.getByTestId("panel-sheet");
    expect(sheet.className).toMatch(/overflow-y-auto/);
    expect(sheet.className).not.toMatch(/overflow-hidden/);
  });
});
