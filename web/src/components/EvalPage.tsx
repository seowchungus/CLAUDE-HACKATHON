import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { EvalResults } from "../types";

const pct = (x: number | null | undefined) => (x == null ? null : `${(x * 100).toFixed(1)}%`);
const num = (x: number | null | undefined, d = 1) => (x == null ? null : Number.isInteger(x) ? String(x) : x.toFixed(d));

function Tile({ label, value, sub, tone = "default" }: { label: string; value: string | null; sub?: string; tone?: "default" | "good" | "bad" }) {
  const cls = value == null ? "text-slate-600" : tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-slate-100";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="text-xs tracking-wider text-slate-400 uppercase">{label}</div>
      <div className={`text-3xl font-black ${cls}`}>{value ?? "not run"}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function JBars({ j }: { j: EvalResults["summary"]["J_mean"] }) {
  const rows: [string, number | null, string][] = [
    ["ACCORD", j.accord, "#22d3ee"],
    ["B1 optimiser", j.B1_optimizer, "#f59e0b"],
    ["B0 FCFS", j.B0_fcfs, "#64748b"],
  ];
  const max = Math.max(1, ...rows.map((r) => r[1] ?? 0));
  return (
    <div className="flex flex-col gap-2">
      {rows.map(([name, v, c]) => (
        <div key={name} className="flex items-center gap-3">
          <span className="w-28 text-sm text-slate-300">{name}</span>
          <div className="h-6 flex-1 rounded bg-slate-900">
            {v != null && <div className="h-6 rounded" style={{ width: `${(v / max) * 100}%`, background: c }} />}
          </div>
          <span className={`w-20 text-right font-mono ${v == null ? "text-slate-600" : ""}`}>{v == null ? "not run" : v.toFixed(2)}</span>
        </div>
      ))}
      <div className="text-xs text-slate-500">Mean fallback cost J (lower is better), same weights for every method.</div>
    </div>
  );
}

export function EvalPage() {
  const [r, setR] = useState<EvalResults | null>(null);
  const [state, setState] = useState<"loading" | "missing" | "error" | "ok">("loading");
  const [err, setErr] = useState("");
  useEffect(() => {
    api.eval().then((x) => { setR(x); setState("ok"); }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) setState("missing");
      else { setErr(String(e)); setState("error"); }
    });
  }, []);

  if (state === "loading") return <div className="p-6 text-slate-500">loading eval…</div>;
  if (state === "missing") return <div className="p-6 text-2xl text-slate-400">Eval not run yet. Run <span className="font-mono">python -m eval.run_eval</span>.</div>;
  if (state === "error" || !r) return <div className="p-6 text-red-400">{err}</div>;
  const s = r.summary;
  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-baseline gap-3">
        <h1 className="text-3xl font-black">Evaluation</h1>
        {r.measured ? (
          <span className="rounded bg-emerald-800 px-2 py-0.5 text-sm font-bold">MEASURED</span>
        ) : (
          <span className="rounded bg-slate-700 px-2 py-0.5 text-sm font-bold text-slate-300">NOT FULLY MEASURED</span>
        )}
        <span className="text-slate-400">N = {r.n} test scenarios (+{r.n_dev} dev) · seed {r.seed} · generated {r.generated_at}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Tile label="Consensus rate" value={pct(s.consensus_rate)} />
        <Tile label="Consensus by R2" value={pct(s.consensus_by_r2)} />
        <Tile label="Fallback rate" value={pct(s.fallback_rate)} />
        <Tile label="Escalate rate" value={pct(s.escalate_rate)} />
        <Tile label="Unsafe proposals blocked" value={num(s.unsafe_proposals_blocked, 0)} tone="good" sub="vetoes + rejected counters" />
        <Tile label="Unsafe plans executed" value={num(s.unsafe_plans_executed, 0)} tone={s.unsafe_plans_executed ? "bad" : "good"} sub="must be 0" />
        <Tile label="Schema failure rate" value={pct(s.schema_failure_rate)} />
        <Tile label="Retry rate" value={pct(s.retry_rate)} />
        <Tile label="Latency p50" value={s.latency_p50_ms == null ? null : `${(s.latency_p50_ms / 1000).toFixed(1)} s`} />
        <Tile label="Latency p95" value={s.latency_p95_ms == null ? null : `${(s.latency_p95_ms / 1000).toFixed(1)} s`} />
        <Tile label="Tokens / resolution" value={num(s.tokens_per_resolution, 0)} />
        <Tile label="Regret vs B1" value={num(s.regret_vs_B1_mean, 2)} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="mb-3 font-semibold text-slate-300">Cost J vs baselines</h2>
          <JBars j={s.J_mean} />
        </section>
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="mb-3 font-semibold text-slate-300">Status quo (2015 DOT, real)</h2>
          <div className="grid grid-cols-3 gap-3">
            <Tile label="Qualifying flights" value={r.status_quo.qualifying_flights?.toLocaleString() ?? null} />
            <Tile label="Weather delay min" value={r.status_quo.weather_delay_min?.toLocaleString() ?? null} />
            <Tile label="Late-aircraft delay min" value={r.status_quo.late_aircraft_delay_min?.toLocaleString() ?? null} />
          </div>
          <h2 className="mt-4 mb-2 font-semibold text-slate-300">vs B0 (FCFS)</h2>
          <div className="grid grid-cols-3 gap-3">
            <Tile label="Bank delay added" value={num(s.vs_B0.bank_delay_added_min)} />
            <Tile label="Misconnected pax" value={num(s.vs_B0.misconnected_pax)} />
            <Tile label="Ramp overtime" value={num(s.vs_B0.ramp_overtime_min)} />
          </div>
        </section>
      </div>
      <section className="rounded-lg border border-slate-800">
        <h2 className="border-b border-slate-800 px-3 py-2 font-semibold text-slate-300">Per scenario</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-400">
              <tr>
                {["scenario", "final state", "rounds", "option", "J", "J B0", "J B1", "unsafe blocked", "latency"].map((h) => (
                  <th key={h} className="px-2 py-1 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.per_scenario.map((p) => {
                const cell = (v: unknown) => (v == null ? <span className="text-slate-600">not run</span> : String(v));
                return (
                  <tr key={p.scenario_id} className="border-t border-slate-800">
                    <td className="px-2 py-1 font-mono">{p.scenario_id}</td>
                    <td className="px-2">{cell(p.final_state)}</td>
                    <td className="px-2">{cell(p.rounds_used)}</td>
                    <td className="px-2 font-mono">{cell(p.option_id)}</td>
                    <td className="px-2 font-mono">{cell(p.J)}</td>
                    <td className="px-2 font-mono">{cell(p.J_B0)}</td>
                    <td className="px-2 font-mono">{cell(p.J_B1)}</td>
                    <td className="px-2">{cell(p.unsafe_blocked)}</td>
                    <td className="px-2">{p.latency_ms == null ? cell(null) : `${(p.latency_ms / 1000).toFixed(1)} s`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
