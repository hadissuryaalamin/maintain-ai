import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { machineA2, sensorsA2 } from "../test/fixtures";
import { MachineBar, formatMetric } from "./MachineBar";
import { SensorSparkline } from "./SensorSparkline";

describe("formatMetric", () => {
  it("turns snake_case metrics into labels", () => {
    expect(formatMetric("vibration_rms")).toBe("Vibration RMS");
    expect(formatMetric("suction_pressure")).toBe("Suction pressure");
  });
});

describe("MachineBar", () => {
  it("shows name, alarm and latest readings", () => {
    render(<MachineBar machine={machineA2} sensors={sensorsA2} onOpenDetails={() => undefined} />);
    expect(screen.getAllByText("A2").length).toBeGreaterThan(0);
    expect(screen.getByText("Process Cooling Pump")).toBeInTheDocument();
    expect(screen.getByText("VIB-HI")).toBeInTheDocument();
    expect(screen.getByText("Vibration RMS")).toBeInTheDocument();
    expect(screen.getByText("7.8 mm/s")).toBeInTheDocument();
    expect(screen.getByText("1.4 bar")).toBeInTheDocument();
  });

  it("shows dash for missing reading", () => {
    const sensors = {
      machine_id: "A2",
      series: [
        {
          metric: "vibration_rms",
          unit: "mm/s",
          latest: { value: null, quality: "missing", recorded_at: "2026-07-20T10:15:00Z" },
          readings: [],
        },
      ],
    };
    render(<MachineBar machine={machineA2} sensors={sensors} onOpenDetails={() => undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
  });

  it("renders a placeholder while no machine is selected", () => {
    render(<MachineBar machine={null} sensors={null} onOpenDetails={() => undefined} />);
    expect(screen.getByText("No machine selected")).toBeInTheDocument();
  });
});

describe("SensorSparkline", () => {
  it("skips null points", () => {
    const series = sensorsA2.series[1]!;
    const { container } = render(<SensorSparkline readings={series.readings} />);
    const points = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(points.trim().split(/\s+/)).toHaveLength(2);
  });

  it("skips readings whose quality is not good", () => {
    const { container } = render(
      <SensorSparkline
        readings={[
          { value: 1.9, quality: "good", recorded_at: "a" },
          { value: 1.8, quality: "good", recorded_at: "b" },
          { value: 1.0, quality: "suspect", recorded_at: "c" },
        ]}
      />,
    );
    const points = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(points.trim().split(/\s+/)).toHaveLength(2);
  });

  it("renders nothing with fewer than two numeric points", () => {
    const { container } = render(
      <SensorSparkline readings={[{ value: 1, quality: "good", recorded_at: "x" }]} />,
    );
    expect(container.querySelector("polyline")).toBeNull();
  });
});
