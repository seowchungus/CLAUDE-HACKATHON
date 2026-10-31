// Hand-written mirror of docs/CONTRACTS.md v1.0. Do not rename fields.

export type AgentRole = "ATC" | "PILOT" | "GROUND";
export const ROLES: AgentRole[] = ["ATC", "PILOT", "GROUND"];

export type ConstraintId =
  | "H1_wake_separation"
  | "H2_runway_capacity"
  | "H3_fuel_reserve"
  | "H4_gate_validity"
  | "H5_crew_duty"
  | "H6_taxiway_reachability"
  | "H7_severe_turbulence";
export const CONSTRAINTS: ConstraintId[] = [
  "H1_wake_separation",
  "H2_runway_capacity",
  "H3_fuel_reserve",
  "H4_gate_validity",
  "H5_crew_duty",
  "H6_taxiway_reachability",
  "H7_severe_turbulence",
];

export type FPAdj = "as_filed" | "speed_reduction" | "hold_10" | "hold_20" | "reroute_weather";
export type WakeCat = "H" | "M" | "L";
export type SizeClass = "S" | "M" | "L";
export type Provenance = "real" | "real_derived" | "estimated" | "synthetic";
export type FlightRole = "disrupted" | "bank" | "connection";
export type ChaosKind = "RUNWAY_CLOSURE" | "TAXIWAY_BLOCK" | "GATE_FAILURE" | "WEATHER_CELL";

export interface DotRow {
  year: number; month: number; day: number;
  airline: string;
  flight_number: number;
  tail_number: string | null;
  origin: string;
  destination: string;
  scheduled_departure: number;
  departure_delay: number | null;
  scheduled_arrival: number;
  arrival_delay: number | null;
  distance: number;
  scheduled_time: number | null;
  air_time: number | null;
  taxi_in: number | null;
  taxi_out: number | null;
  weather_delay: number | null;
  late_aircraft_delay: number | null;
  air_system_delay: number | null;
}

export interface Airport { iata: string; name: string; city: string; state: string; lat: number; lon: number }

export interface FlightRef {
  flight_id: string;
  airline: string;
  flight_number: number;
  tail_number: string | null;
  origin: string;
  destination: string;
  sched_dep_min: number;
  sched_arr_min: number;
  est_arr_min: number | null;
  role: FlightRole;
  wake: WakeCat;
  pax_connecting?: number | null;
}

export interface Gate {
  gate_id: string;
  concourse: string;
  size: SizeClass;
  taxi_path: string[];
  occupied: [number, number][];
  out_of_service: boolean;
}

export interface ChaosEvent { kind: ChaosKind; params: Record<string, unknown>; note: string }

export interface Scenario {
  scenario_id: string;
  seed: number;
  fixture: boolean;
  row: DotRow;
  disruption_type: "WEATHER" | "LATE_AIRCRAFT";
  disruption_min: number;
  origin: Airport;
  destination: Airport;
  disrupted: FlightRef;
  bank: FlightRef[];
  connections: FlightRef[];
  base_eta_min: number;
  aar_nominal: number;
  aar_reduced: number;
  aircraft_size: SizeClass;
  fuel_at_fix_min: number;
  flight_crew_duty_remaining_min: number;
  ramp_shift_end_min: number;
  next_departure_min: number | null;
  gates: Gate[];
  taxiways: string[];
  blocked_taxiways: string[];
  turbulence_by_fp: Record<string, number>;
  chaos_applied: ChaosEvent[];
  provenance: Record<string, Provenance>;
  // v1.2 (organisers' workbook)
  airport_limits?: AirportLimits | Record<string, never>;
  planned_gate?: string | null;
  decision_time_min?: number | null;
}

export interface AirportLimits {
  size_class?: string;
  active_runways?: number;
  gates?: number;
  max_runway_ops_per_hour?: number;
  min_turnaround_min?: number;
  spare_gates_at_any_time?: number;
  [k: string]: unknown;
}

export interface Metrics {
  eta_new_min: number;
  runway_slot_min: number;
  separation_margin_s: number;
  fuel_at_landing_min: number;
  extra_fuel_min: number;
  hold_min: number;
  turbulence_idx: number;
  misconnected_pax: number;
  gate: string;
  gate_free_from_min: number;
  gate_free_to_min: number;
  taxi_path_ok: boolean;
  turnaround_buffer_min: number;
  ramp_overtime_min: number;
  bank_delay_added_min: number;
  arrivals_this_hour: number;
  throughput_loss: number;
  cost_J: number;
  // v1.2
  gate_change?: boolean;
  gate_change_notice_min?: number | null;
  fuel_at_landing_kg?: number | null;
}

export interface Option {
  option_id: string;
  eta_shift_min: number;
  gate: string;
  fp_adjustment: FPAdj;
  source: "generated" | "counter" | "fcfs";
  proposed_by: AgentRole | null;
  parent_option: string | null;
  label: string;
  metrics: Metrics;
}

export interface ConstraintResult {
  option_id: string;
  constraint_id: ConstraintId;
  passed: boolean;
  value: number | null;
  threshold: number | null;
  detail: string;
}

export interface CheckReport { option_id: string; feasible: boolean; results: ConstraintResult[] }

export interface FallbackResult {
  status: "PLAN" | "ESCALATE";
  option_id: string | null;
  cost_J: number | null;
  ranking: [string, number][];
  weights: Record<string, number>;
  reason: string;
}

export interface ScenarioSummary {
  scenario_id: string;
  date: string;
  flight_id: string;
  origin: string;
  destination: string;
  disruption_type: "WEATHER" | "LATE_AIRCRAFT";
  disruption_min: number;
}

export interface ScenarioBundle {
  scenario: Scenario;
  options: Option[];
  checks: Record<string, CheckReport>;
  fallback: FallbackResult;
  fcfs: Option;
}

// §2 agent messages
export interface Counter { base_option: string; param: "eta_shift_min" | "gate" | "fp_adjustment"; value: string | number }
export type Action = "PROPOSE" | "COUNTER" | "ACCEPT" | "REJECT";

export interface AgentPosition {
  agent: AgentRole;
  round: 1 | 2 | 3;
  action: Action;
  ranking: string[];
  acceptable: string[];
  counter: Counter | null;
  red_lines: ConstraintId[];
  cites: string[];
  rationale: string;
}

export interface AgentMessage {
  agent: AgentRole;
  round: number;
  status: "ok" | "schema_fail" | "timeout" | "rate_limited" | "error" | "killed";
  position: AgentPosition | null;
  errors: string[];
  model: string;
  latency_ms: number;
  tokens_in: number | null;
  tokens_out: number | null;
  retries: number;
  ungrounded: boolean;
}

// §3 SSE
export interface RunStartedData {
  scenario_id: string;
  max_rounds: number;
  llm_enabled: boolean;
  models: Record<string, string>;
  parent_run_id: string | null;
  chaos_applied: ChaosEvent[];
  scripted?: boolean; // additive (W2-03): MockLLMClient scripted failure modes
  mode?: string;
}
export interface OptionsData { options: Option[]; checks: Record<string, CheckReport>; fallback: FallbackResult; fcfs: Option }
export interface RoundStartedData { round: number; phase: "PROPOSE" | "RESPOND" | "BALLOT"; candidates: string[]; tentative: string | null }
export interface AgentThinkingData { round: number; agent: AgentRole }
export interface CounterCheckedData {
  round: number; agent: AgentRole; counter: Counter; accepted: boolean;
  option_id: string | null; reason: string; check: CheckReport | null; failed?: ConstraintId[];
}
export interface VetoData { round: number; option_id: string; agents: AgentRole[]; failed: ConstraintId[]; reason: string }
export interface TentativeData { round: number; option_id: string | null; agreement_set: string[]; minmax_rank: Record<string, number> }
export interface RoundEndedData { round: number; all_accept: boolean; actions: Record<AgentRole, Action | null> }
export interface ConsensusData { round: number; option_id: string; plan: Option; check: CheckReport; accepts: Record<AgentRole, string> }
export interface FallbackData {
  reason: "NO_CONSENSUS" | "LLM_KILLED" | "LLM_ERROR" | "NO_FEASIBLE";
  result: FallbackResult;
  plan: Option | null;
}
export interface NarrationData { text: string }
export interface AwaitingApprovalData { decision_source: "CONSENSUS" | "FALLBACK" | "ESCALATE"; option_id: string | null; rounds_used: number }
export interface ApprovedData { action: "APPROVE" | "OVERRIDE"; option_id: string; by: string; note: string; final_hash: string }
export interface RunEndedData {
  final_state: "CONSENSUS" | "FALLBACK" | "ESCALATE" | "SUPERSEDED";
  rounds_used: number; latency_ms: number; chain_ok: boolean; n_llm_calls: number;
}
export interface ErrorData { message: string; fatal: boolean }

export interface EventMap {
  run_started: RunStartedData;
  options: OptionsData;
  round_started: RoundStartedData;
  agent_thinking: AgentThinkingData;
  agent_position: AgentMessage;
  counter_checked: CounterCheckedData;
  veto: VetoData;
  tentative: TentativeData;
  round_ended: RoundEndedData;
  consensus: ConsensusData;
  fallback: FallbackData;
  narration: NarrationData;
  awaiting_approval: AwaitingApprovalData;
  approved: ApprovedData;
  run_ended: RunEndedData;
  error: ErrorData;
}
export type EventType = keyof EventMap;
export const EVENT_TYPES: EventType[] = [
  "run_started", "options", "round_started", "agent_thinking", "agent_position", "counter_checked",
  "veto", "tentative", "round_ended", "consensus", "fallback", "narration", "awaiting_approval",
  "approved", "run_ended", "error",
];

export type Envelope = {
  [K in EventType]: { type: K; run_id: string; seq: number; ts: string; log_hash: string; data: EventMap[K] };
}[EventType];

// §4
export interface LLMBudget {
  keys: Record<string, { used_today: number; cap: number; remaining: number; rpm_cap: number }>;
  enforce: boolean;
  resets_at: string;
}
export interface Health {
  ok: boolean; llm_enabled: boolean; models: Record<string, string>; data_loaded: boolean; mock: boolean;
  llm_budget?: LLMBudget | null;
}
export interface Limits {
  workbook: { wake_separation: Record<string, number>; fuel_and_crew: Record<string, unknown>; rules_of_play: Record<string, unknown> };
  airport: AirportLimits | null;
  deviations: string[];
}

// §6 eval/results.json (null = not run, never 0)
export interface EvalResults {
  generated_at: string; n: number; n_dev: number; seed: number;
  status_quo: { qualifying_flights: number | null; weather_delay_min: number | null; late_aircraft_delay_min: number | null };
  summary: {
    consensus_rate: number | null; consensus_by_r2: number | null; consensus_by_r3: number | null;
    fallback_rate: number | null; escalate_rate: number | null;
    unsafe_proposals_blocked: number | null; unsafe_plans_executed: number | null;
    schema_failure_rate: number | null; retry_rate: number | null;
    latency_p50_ms: number | null; latency_p95_ms: number | null; tokens_per_resolution: number | null;
    J_mean: { accord: number | null; B0_fcfs: number | null; B1_optimizer: number | null };
    regret_vs_B1_mean: number | null;
    vs_B0: { bank_delay_added_min: number | null; misconnected_pax: number | null; ramp_overtime_min: number | null };
    [k: string]: unknown;
  };
  ablations: Record<string, unknown>;
  per_scenario: {
    scenario_id: string; final_state: string | null; rounds_used: number | null; option_id: string | null;
    J: number | null; J_B0: number | null; J_B1: number | null; unsafe_blocked: number | null;
    latency_ms: number | null; run_id: string | null; [k: string]: unknown;
  }[];
  measured: boolean;
  llm?: "live" | "mock" | "none" | string;
  bad_day?: {
    airport: string; date: string; n_flights: number;
    B0: Record<string, unknown> | null; B1: Record<string, unknown> | null;
    b0_infeasible: number | null; b1_escalate: number | null;
  } | null;
}

export interface MapAirport { iata: string; name: string; lat: number; lon: number; role: "origin" | "destination" | "other" }
export interface MapFlight {
  flight_id: string;
  role: FlightRole;
  origin: string; destination: string;
  origin_lat: number; origin_lon: number;
  dest_lat: number; dest_lon: number;
  sched_dep_min: number; sched_arr_min: number;
  est_arr_min: number | null;
  position_estimated: boolean;
}
export interface MapPayload { focus_airport: string; airports: MapAirport[]; flights: MapFlight[]; now_min: number }
export interface ScenarioResponse { bundle: ScenarioBundle; map: MapPayload }

// §5
export interface LogEntry {
  seq: number; ts: string; run_id: string; scenario_id: string;
  source_row: Record<string, unknown>;
  event_type: string; actor: string;
  constraint_ids: string[]; synthetic_fields: string[];
  payload: Record<string, unknown>;
  prev_hash: string; hash: string;
}
export interface VerifyResult { ok: boolean; n_entries: number; head_hash: string; broken_at: number | null }

export const hhmm = (min: number | null | undefined): string => {
  if (min == null) return "--:--";
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}${min >= 1440 ? "+1" : ""}`;
};
export const shortC = (c: string) => c.split("_")[0];
