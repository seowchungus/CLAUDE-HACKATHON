import type {
  ChaosEvent, EvalResults, Health, Limits, LogEntry, ScenarioResponse, ScenarioSummary, VerifyResult,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) {
    let msg = await r.text();
    try {
      msg = JSON.parse(msg).detail ?? msg;
    } catch {
      /* plain text */
    }
    throw new ApiError(r.status, `${r.status}: ${msg}`);
  }
  return r.json() as Promise<T>;
}
const post = <T>(path: string, body: unknown) => j<T>(path, { method: "POST", body: JSON.stringify(body) });

export type ScriptedMode = "deadlock" | "unsafe" | "hallucinate";

export const api = {
  health: () => j<Health>("/api/health"),
  limits: (scenarioId?: string) => j<Limits>(`/api/limits${scenarioId ? `?scenario_id=${encodeURIComponent(scenarioId)}` : ""}`),
  scenarios: () => j<ScenarioSummary[]>("/api/scenarios"),
  scenario: (id: string) => j<ScenarioResponse>(`/api/scenarios/${encodeURIComponent(id)}`),
  runBundle: (runId: string) => j<ScenarioResponse>(`/api/runs/${runId}/bundle`),
  createRun: (scenario_id: string, mode?: ScriptedMode) =>
    post<{ run_id: string }>("/api/runs", mode ? { scenario_id, mode } : { scenario_id }),
  chaos: (runId: string, ev: ChaosEvent) => post<{ run_id: string; parent_run_id: string }>(`/api/runs/${runId}/chaos`, ev),
  approve: (runId: string, action: "APPROVE" | "OVERRIDE", option_id: string, by: string, note = "") =>
    post<{ ok: boolean; final_hash: string }>(`/api/runs/${runId}/approve`, { action, option_id, by, note }),
  kill: (llm_enabled: boolean) => post<{ llm_enabled: boolean }>("/api/kill", { llm_enabled }),
  log: async (runId: string): Promise<LogEntry[]> => {
    const r = await fetch(`${BASE}/api/runs/${runId}/log`);
    if (!r.ok) throw new ApiError(r.status, `${r.status}`);
    return (await r.text()).split("\n").filter(Boolean).map((l) => JSON.parse(l));
  },
  logUrl: (runId: string) => `${BASE}/api/runs/${runId}/log`,
  verify: (runId: string) => j<VerifyResult>(`/api/runs/${runId}/verify`),
  eval: () => j<EvalResults>("/api/eval"),
  replays: () => j<string[]>("/api/replay"),
  /** key = a run_id, or "replay:<name>" for a recorded hero run */
  streamUrl: (key: string) =>
    key.startsWith("replay:") ? `${BASE}/api/replay/${encodeURIComponent(key.slice(7))}/stream` : `${BASE}/api/runs/${key}/stream`,
};
