import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient } from "../api/client";
import type { ApprovalDecisionResponse } from "../api/types";
import { diagnoseAwaitingApproval } from "../test/fixtures";
import { APPROVAL_FOOTER, ApprovalCard } from "./ApprovalCard";

const approval = diagnoseAwaitingApproval.pending_approval!;

function clientWith(decideApproval: ApiClient["decideApproval"]): ApiClient {
  return { listMachines: vi.fn(), getMachineSensors: vi.fn(), diagnose: vi.fn(), decideApproval };
}

const approvedResponse: ApprovalDecisionResponse = {
  approval_id: approval.approval_id,
  status: "approved",
  result: { work_order_id: "WO-00042", status: "draft" },
};

describe("ApprovalCard", () => {
  it("shows the exact footer copy and proposed fields", () => {
    render(<ApprovalCard approval={approval} client={clientWith(vi.fn())} />);
    expect(APPROVAL_FOOTER).toBe("Creates a draft only. No equipment action is taken.");
    expect(screen.getByText(APPROVAL_FOOTER)).toBeInTheDocument();
    expect(screen.getByText(approval.message)).toBeInTheDocument();
    expect(screen.getByText("Inspect pump inlet")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("approve sends approved:true with idempotency key and shows work order id", async () => {
    const decide = vi.fn().mockResolvedValue(approvedResponse);
    render(<ApprovalCard approval={approval} client={clientWith(decide)} />);
    await userEvent.click(screen.getByRole("button", { name: "Approve & create draft" }));
    expect(decide).toHaveBeenCalledWith(approval.approval_id, {
      approved: true,
      idempotency_key: expect.stringMatching(/^.{8,128}$/),
    });
    expect(await screen.findByText("Draft created")).toBeInTheDocument();
    expect(screen.getByText("WO-00042")).toBeInTheDocument();
    expect(screen.queryByText(/needs your approval/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve & create draft" })).toBeNull();
  });

  it("double tap sends one request", async () => {
    let resolve: (value: ApprovalDecisionResponse) => void = () => undefined;
    const decide = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)));
    render(<ApprovalCard approval={approval} client={clientWith(decide)} />);
    const button = screen.getByRole("button", { name: "Approve & create draft" });
    await userEvent.dblClick(button);
    await userEvent.click(button);
    expect(decide).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    resolve(approvedResponse);
    expect(await screen.findByText("Draft created")).toBeInTheDocument();
  });

  it("retry after error reuses idempotency key", async () => {
    const decide = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("Could not reach the server.", null))
      .mockResolvedValueOnce(approvedResponse);
    render(<ApprovalCard approval={approval} client={clientWith(decide)} />);
    await userEvent.click(screen.getByRole("button", { name: "Approve & create draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
    await userEvent.click(screen.getByRole("button", { name: "Approve & create draft" }));
    expect(await screen.findByText("Draft created")).toBeInTheDocument();
    const firstKey = decide.mock.calls[0]![1].idempotency_key;
    expect(decide.mock.calls[1]![1].idempotency_key).toBe(firstKey);
  });

  it("reject shows Rejected and disables buttons", async () => {
    const decide = vi
      .fn()
      .mockResolvedValue({ approval_id: approval.approval_id, status: "rejected", result: null });
    render(<ApprovalCard approval={approval} client={clientWith(decide)} />);
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(decide).toHaveBeenCalledWith(approval.approval_id, {
      approved: false,
      idempotency_key: expect.any(String),
    });
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("renders only proposed_action fields that exist", () => {
    render(
      <ApprovalCard
        approval={{ ...approval, proposed_action: { machine_id: "A1", extra: "ignored" } }}
        client={clientWith(vi.fn())}
      />,
    );
    expect(screen.getByText("Machine")).toBeInTheDocument();
    expect(screen.queryByText("Title")).toBeNull();
    expect(screen.queryByText("Priority")).toBeNull();
    expect(screen.queryByText("ignored")).toBeNull();
  });
});
