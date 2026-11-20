import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { machineA1, machineA2 } from "../test/fixtures";
import { Composer, DISCLAIMER, QUICK_PROMPTS } from "./Composer";

function setup(overrides: Partial<Parameters<typeof Composer>[0]> = {}) {
  const props = {
    onSend: vi.fn(),
    sending: false,
    machines: [machineA1, machineA2],
    selected: machineA2,
    onSelectMachine: vi.fn(),
    ...overrides,
  };
  render(<Composer {...props} />);
  return props;
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
});

describe("Composer", () => {
  it("disables send under 3 chars", async () => {
    const props = setup();
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "ab");
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "c");
    expect(send).toBeEnabled();
    await userEvent.click(send);
    expect(props.onSend).toHaveBeenCalledWith("abc");
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
  });

  it("Enter sends, Shift+Enter adds a newline", async () => {
    const props = setup();
    const box = screen.getByRole("textbox", { name: "Message" });
    await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(box).toHaveValue("line one\nline two");
    await userEvent.type(box, "{Enter}");
    expect(props.onSend).toHaveBeenCalledWith("line one\nline two");
  });

  it("chip inserts text without sending", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("button", { name: QUICK_PROMPTS[0] }));
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(QUICK_PROMPTS[0]);
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("does not send while a request is pending", async () => {
    const props = setup({ sending: true });
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "noise again{Enter}");
    expect(props.onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("limits messages to 10000 characters", () => {
    setup();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveAttribute("maxLength", "10000");
  });

  it("mic hidden when unsupported", () => {
    setup();
    expect(screen.queryByRole("button", { name: /dictate/i })).toBeNull();
  });

  it("mic shown when speech recognition exists", () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = vi.fn();
    setup();
    expect(screen.getByRole("button", { name: /dictate/i })).toBeInTheDocument();
  });

  it("quick chips and machine chip are glove-sized", () => {
    setup();
    expect(screen.getByRole("button", { name: QUICK_PROMPTS[0] }).className).toMatch(/(^| )h-12( |$)/);
    expect(screen.getByRole("combobox", { name: "Machine" }).parentElement!.className).toMatch(/min-h-12/);
  });

  it("shows the disclaimer and the machine chip", () => {
    setup();
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
    expect(DISCLAIMER).toBe(
      "AI suggestions are preliminary. Verify with the OEM manual and site procedures.",
    );
    expect(screen.getByRole("combobox", { name: "Machine" })).toHaveValue("A2");
  });
});
