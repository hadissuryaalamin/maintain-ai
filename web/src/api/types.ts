// Hand-written mirrors of app/schemas/api.py and app/schemas/diagnostic.py.
// Decimal fields arrive as JSON strings (pydantic) but are typed loosely on purpose.

export type DecimalValue = string | number;

export interface MachineSummary {
  id: string;
  name: string;
  model: string;
  line: string;
  status: string;
  condition: string | null;
  active_alarm: string | null;
  criticality: string | null;
  hourly_downtime_cost: DecimalValue;
  cost_currency: string | null;
  last_status_at: string | null;
}

export interface SensorPointOut {
  value: number | null;
  quality: string;
  recorded_at: string;
}

export interface SensorSeries {
  metric: string;
  unit: string;
  latest: SensorPointOut | null;
  readings: SensorPointOut[];
}

export interface MachineSensors {
  machine_id: string;
  series: SensorSeries[];
}

export type Confidence = "low" | "medium" | "high";
export type SourceType = "tool" | "manual" | "incident_history" | "user";

export interface Observation {
  statement: string;
  source_type: SourceType;
  source_reference: string;
}

export interface PossibleCause {
  cause: string;
  confidence: Confidence;
  reasoning_summary: string;
}

export interface RecommendedAction {
  step: number;
  action: string;
  requires_shutdown: boolean;
  requires_approval: boolean;
}

export interface DiagnosticResult {
  incident_summary: string;
  observations: Observation[];
  possible_causes: PossibleCause[];
  recommended_actions: RecommendedAction[];
  missing_information: string[];
  safety_notice: string;
}

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
}

export interface DiagnoseRequest {
  message: string;
  conversation_history?: ConversationMessage[];
  optimization_mode?: "baseline" | "optimized";
  task_type?: string;
}

export interface ToolTraceItem {
  tool_name: string;
  call_id: string;
  status: string;
  arguments: Record<string, unknown>;
  result_preview: string;
  latency_ms: number;
  error_category: string | null;
}

export interface UsageSummary {
  model: string;
  provider: string;
  model_requests: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  estimated_total_cost: DecimalValue | null;
  latency_ms: number;
  usage_is_estimated: boolean;
}

export interface PendingApproval {
  approval_id: string;
  tool_name: string;
  proposed_action: Record<string, unknown>;
  message: string;
}

export interface DiagnoseResponse {
  run_id: string;
  status: string;
  diagnostic: DiagnosticResult | null;
  pending_approval: PendingApproval | null;
  tool_trace: ToolTraceItem[];
  usage: UsageSummary;
  error: string | null;
}

export interface ApprovalDecisionRequest {
  approved: boolean;
  idempotency_key: string;
}

export interface ApprovalDecisionResponse {
  approval_id: string;
  status: string;
  result: Record<string, unknown> | null;
}
