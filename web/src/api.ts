import type { ChaosEvent, Health, LogEntry, ScenarioResponse, ScenarioSummary, VerifyResult } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}
const post = <T>(path: string, body: unknown) => j<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => j<Health>("/api/health"),
  scenarios: () => j<ScenarioSummary[]>("/api/scenarios"),
  scenario: (id: string) => j<ScenarioResponse>(`/api/scenarios/${encodeURIComponent(id)}`),
  createRun: (scenario_id: string) => post<{ run_id: string }>("/api/runs", { scenario_id }),
  chaos: (runId: string, ev: ChaosEvent) => post<{ run_id: string; parent_run_id: string }>(`/api/runs/${runId}/chaos`, ev),
  approve: (runId: string, action: "APPROVE" | "OVERRIDE", option_id: string, by: string, note = "") =>
    post<{ ok: boolean; final_hash: string }>(`/api/runs/${runId}/approve`, { action, option_id, by, note }),
  kill: (llm_enabled: boolean) => post<{ llm_enabled: boolean }>("/api/kill", { llm_enabled }),
  log: async (runId: string): Promise<LogEntry[]> => {
    const r = await fetch(`${BASE}/api/runs/${runId}/log`);
    if (!r.ok) throw new Error(`${r.status}`);
    return (await r.text()).split("\n").filter(Boolean).map((l) => JSON.parse(l));
  },
  logUrl: (runId: string) => `${BASE}/api/runs/${runId}/log`,
  verify: (runId: string) => j<VerifyResult>(`/api/runs/${runId}/verify`),
  streamUrl: (runId: string) => `${BASE}/api/runs/${runId}/stream`,
};
