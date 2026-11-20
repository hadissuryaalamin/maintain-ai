import type { DiagnoseResponse, MachineSensors, MachineSummary } from "../api/types";

const usage = {
  model: "demo-maintenance-v1",
  provider: "demo",
  model_requests: 2,
  input_tokens: 1200,
  output_tokens: 300,
  cached_input_tokens: 0,
  estimated_total_cost: null,
  latency_ms: 40,
  usage_is_estimated: true,
};

export const machineA1: MachineSummary = {
  id: "A1",
  name: "Line 3 Servo Press",
  model: "SP-400",
  line: "Line 3",
  status: "stopped",
  condition: null,
  active_alarm: "E217",
  criticality: "high",
  hourly_downtime_cost: "4800.00",
  cost_currency: "USD",
  last_status_at: "2026-07-20T10:15:00Z",
};

export const machineA2: MachineSummary = {
  id: "A2",
  name: "Process Cooling Pump",
  model: "CP-200",
  line: "Utilities",
  status: "running",
  condition: "warning",
  active_alarm: "VIB-HI",
  criticality: "medium",
  hourly_downtime_cost: "1800.00",
  cost_currency: "USD",
  last_status_at: "2026-07-20T10:15:00Z",
};

export const machineB1: MachineSummary = {
  ...machineA1,
  id: "B1",
  name: "Packaging Conveyor",
  model: "CV-120",
  line: "Packaging Line 1",
  active_alarm: "TRK-04",
};

const at = (minute: number) => `2026-07-20T10:${String(minute).padStart(2, "0")}:00Z`;

export const sensorsA2: MachineSensors = {
  machine_id: "A2",
  series: [
    {
      metric: "suction_pressure",
      unit: "bar",
      latest: { value: 1.4, quality: "good", recorded_at: at(15) },
      readings: [
        { value: 1.9, quality: "good", recorded_at: at(5) },
        { value: 1.6, quality: "good", recorded_at: at(10) },
        { value: 1.4, quality: "good", recorded_at: at(15) },
      ],
    },
    {
      metric: "vibration_rms",
      unit: "mm/s",
      latest: { value: 7.8, quality: "good", recorded_at: at(15) },
      readings: [
        { value: 4.6, quality: "good", recorded_at: at(5) },
        { value: null, quality: "missing", recorded_at: at(10) },
        { value: 7.8, quality: "good", recorded_at: at(15) },
      ],
    },
  ],
};

export const diagnoseCompleted: DiagnoseResponse = {
  run_id: "9566e417-4210-4ca4-a9c7-4584a54c7afc",
  status: "completed",
  diagnostic: {
    incident_summary: "Preliminary diagnostic for A2 based on 4 evidence items.",
    observations: [
      {
        statement: "VIB-HI reports elevated vibration; it does not identify a root cause.",
        source_type: "manual",
        source_reference: "manual:manual-a-cp200:v1.0.0#CP200-ALARM-VIBHI",
      },
      {
        statement: "Historical incident INC-A-004 for machine A2 was retrieved for comparison.",
        source_type: "incident_history",
        source_reference: "incident:INC-A-004",
      },
      {
        statement: "Latest vibration_rms reading was 7.8 mm/s.",
        source_type: "tool",
        source_reference: "tool:get_sensor_history:A2:vibration_rms",
      },
    ],
    possible_causes: [
      {
        cause: "Restricted inlet flow or possible cavitation",
        confidence: "medium",
        reasoning_summary: "Vibration rose while suction pressure fell.",
      },
      {
        cause: "Coupling misalignment",
        confidence: "low",
        reasoning_summary: "Less consistent with falling suction pressure.",
      },
    ],
    recommended_actions: [
      {
        step: 2,
        action: "Check suction line for leaks or air ingress.",
        requires_shutdown: false,
        requires_approval: false,
      },
      {
        step: 1,
        action: "Follow site lockout/tagout before invasive inspection.",
        requires_shutdown: true,
        requires_approval: false,
      },
      {
        step: 3,
        action: "Create a draft work order for inspection.",
        requires_shutdown: false,
        requires_approval: true,
      },
    ],
    missing_information: ["Vibration history is incomplete."],
    safety_notice: "Preliminary decision support only. Follow site procedures.",
  },
  pending_approval: null,
  tool_trace: [
    {
      tool_name: "get_machine_status",
      call_id: "c1",
      status: "succeeded",
      arguments: {},
      result_preview: "",
      latency_ms: 1,
      error_category: null,
    },
    {
      tool_name: "search_manual",
      call_id: "c2",
      status: "failed",
      arguments: {},
      result_preview: "",
      latency_ms: 12,
      error_category: "timeout",
    },
  ],
  usage,
  error: null,
};

export const diagnoseAwaitingApproval: DiagnoseResponse = {
  run_id: "b2a1c3d4-0000-4000-8000-000000000001",
  status: "awaiting_approval",
  diagnostic: null,
  pending_approval: {
    approval_id: "e497c9f6-f801-450d-b452-7f49edecee11",
    tool_name: "create_work_order",
    proposed_action: {
      machine_id: "A2",
      title: "Inspect pump inlet",
      description: "Inspect pump inlet and suction line for restriction or air ingress.",
      priority: "high",
    },
    message:
      "Review the exact proposed change and explicitly approve or reject it. No work order has been created.",
  },
  tool_trace: [],
  usage,
  error: null,
};

export const diagnoseFailed: DiagnoseResponse = {
  run_id: "f0f0f0f0-1111-4222-8333-444444444444",
  status: "failed",
  diagnostic: null,
  pending_approval: null,
  tool_trace: [],
  usage,
  error: "Model request failed safely.",
};
