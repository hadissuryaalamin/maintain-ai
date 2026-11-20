import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../api/client";
import type { DiagnoseResponse } from "../api/types";
import type { AssistantTurn as AssistantTurnData } from "../state/conversations";
import { IdentityProvider } from "../state/identity";
import {
  diagnoseAwaitingApproval,
  diagnoseCompleted,
  diagnoseFailed,
  machineA2,
} from "../test/fixtures";
import { AssistantTurn, STATUS_COPY } from "./AssistantTurn";

const client: ApiClient = {
  listMachines: vi.fn(),
  getMachineSensors: vi.fn(),
  diagnose: vi.fn(),
  decideApproval: vi.fn(),
};

function wrap(node: ReactNode) {
  return (
    <IdentityProvider initial={{ tenantId: "company-a", userId: "user-a-tech" }} clientFactory={() => client}>
      {node}
    </IdentityProvider>
  );
}

function done(response: DiagnoseResponse): AssistantTurnData {
  return { id: "t1", role: "assistant", at: "2026-11-21T06:42:18Z", state: "done", response };
}

function renderTurn(turn: AssistantTurnData, handlers: Partial<Record<"onDraftWorkOrder" | "onRetry" | "onFollowUp", () => void>> = {}) {
  const props = {
    onDraftWorkOrder: vi.fn(),
    onRetry: vi.fn(),
    onFollowUp: vi.fn(),
    ...handlers,
  };
  const view = render(wrap(<AssistantTurn turn={turn} machine={machineA2} {...props} />));
  return { ...view, props };
}

describe("AssistantTurn", () => {
  it("shows the read-only status line", () => {
    renderTurn(done(diagnoseCompleted));
    expect(STATUS_COPY).toBe("Read-only access · cannot control equipment");
    expect(screen.getByText(STATUS_COPY)).toBeInTheDocument();
  });

  it("renders likely cause, alternatives and confidence word", () => {
    renderTurn(done(diagnoseCompleted));
    const likely = screen.getByRole("region", { name: "Likely cause" });
    expect(within(likely).getByText("Restricted inlet flow or possible cavitation")).toBeInTheDocument();
    expect(within(likely).getByText("Vibration rose while suction pressure fell.")).toBeInTheDocument();
    expect(within(likely).getByText("Medium confidence")).toBeInTheDocument();
    const alternatives = screen.getByRole("region", { name: "Alternatives" });
    expect(within(alternatives).getByText("Coupling misalignment")).toBeInTheDocument();
    expect(within(alternatives).getByText("Low confidence")).toBeInTheDocument();
    expect(screen.getByText(diagnoseCompleted.diagnostic!.incident_summary)).toBeInTheDocument();
  });

  it("renders evidence with source references", () => {
    renderTurn(done(diagnoseCompleted));
    const evidence = screen.getByRole("region", { name: "Evidence" });
    expect(within(evidence).getAllByRole("listitem")).toHaveLength(3);
    expect(within(evidence).getByText("manual:manual-a-cp200:v1.0.0#CP200-ALARM-VIBHI")).toBeInTheDocument();
    expect(within(evidence).getByText("incident:INC-A-004")).toBeInTheDocument();
  });

  it("renders steps in order with shutdown and approval badges", () => {
    renderTurn(done(diagnoseCompleted));
    const steps = within(screen.getByRole("region", { name: "Recommended checks" })).getAllByRole("listitem");
    expect(steps.map((step) => step.textContent)).toEqual([
      expect.stringContaining("Follow site lockout/tagout"),
      expect.stringContaining("Check suction line"),
      expect.stringContaining("Create a draft work order"),
    ]);
    expect(within(steps[0]!).getByText("Requires shutdown")).toBeInTheDocument();
    expect(within(steps[2]!).getByText("Requires approval")).toBeInTheDocument();
  });

  it("renders safety notice verbatim and missing information", () => {
    renderTurn(done(diagnoseCompleted));
    expect(screen.getByText(diagnoseCompleted.diagnostic!.safety_notice)).toBeInTheDocument();
    const missing = screen.getByRole("region", { name: "Missing information" });
    expect(within(missing).getByText("Vibration history is incomplete.")).toBeInTheDocument();
  });

  it("hides missing information when empty", () => {
    const response = {
      ...diagnoseCompleted,
      diagnostic: { ...diagnoseCompleted.diagnostic!, missing_information: [] },
    };
    renderTurn(done(response));
    expect(screen.queryByRole("region", { name: "Missing information" })).toBeNull();
  });

  it("tool trace collapsed shows count, expands on click", async () => {
    renderTurn(done(diagnoseCompleted));
    const toggle = screen.getByRole("button", { name: /Used 2 tools/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("get_machine_status")).toBeNull();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("get_machine_status")).toBeInTheDocument();
    expect(screen.getByText("12 ms")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });

  it("shows downtime chip from the selected machine", () => {
    renderTurn(done(diagnoseCompleted));
    expect(screen.getByText("~$1,800/hr if stopped · medium criticality")).toBeInTheDocument();
  });

  it("draft and follow-up actions call handlers", async () => {
    const { props } = renderTurn(done(diagnoseCompleted));
    await userEvent.click(screen.getByRole("button", { name: "Draft work order" }));
    await userEvent.click(screen.getByRole("button", { name: "Ask follow-up" }));
    expect(props.onDraftWorkOrder).toHaveBeenCalledOnce();
    expect(props.onFollowUp).toHaveBeenCalledOnce();
  });

  it("failed response shows error and run id, no diagnosis card", async () => {
    const { props } = renderTurn(done(diagnoseFailed));
    expect(screen.getByRole("alert")).toHaveTextContent("Model request failed safely.");
    expect(screen.getByText(/Run f0f0f0f0/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Likely cause" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(props.onRetry).toHaveBeenCalledOnce();
  });

  it("transport error turn shows message and retry", () => {
    renderTurn({
      id: "e1",
      role: "assistant",
      at: "2026-11-21T06:42:18Z",
      state: "error",
      message: "Could not reach the server.",
      retryText: "x",
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the server.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("pending turn shows progress copy", () => {
    renderTurn({ id: "p1", role: "assistant", at: "2026-11-21T06:42:18Z", state: "pending" });
    expect(screen.getByText("Checking machine data…")).toBeInTheDocument();
  });

  it("awaiting approval without diagnostic is not an error", () => {
    renderTurn(done(diagnoseAwaitingApproval));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(diagnoseAwaitingApproval.pending_approval!.message)).toBeInTheDocument();
  });

  it("never renders forbidden strings or numeric confidence", () => {
    const { container } = renderTurn(done(diagnoseCompleted));
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/SCADA|Emergency|Dispatch|Live stream/i);
    expect(text).not.toMatch(/\b0\.\d{2}\b/);
  });
});
