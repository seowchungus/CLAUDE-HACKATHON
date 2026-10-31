import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { EvalResults } from "../types";

const pct = (x: number | null | undefined) => (x == null ? null : `${(x * 100).toFixed(1)}%`);
const num = (x: number | null | undefined, d = 1) => (x == null ? null : Number.isInteger(x) ? String(x) : x.toFixed(d));

function Tile({ label, value, sub, tone = "default", scripted = false }: { label: string; value: string | null; sub?: string; tone?: "default" | "good" | "bad"; scripted?: boolean }) {
  const cls = value == null || scripted ? "text-slate-600" : tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-slate-100";
  if (scripted) sub = "scripted agents, not an LLM result";
  return (
    <div className={`rounded-lg border p-3 ${scripted ? "border-dashed border-amber-900 bg-slate-950" : "border-slate-800 bg-slate-900"}`} title={scripted ? "Mock run: these numbers come from scripted agents (MockLLMClient), not Gemini" : undefined}>
      <div className="text-xs tracking-wider text-slate-400 uppercase">{label}</div>
      <div className={`text-3xl font-black ${cls}`}>{value ?? "not run"}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function JBars({ j, accordLabel = "ACCORD" }: { j: EvalResults["summary"]["J_mean"]; accordLabel?: string }) {
  const rows: [string, number | null, string][] = [
    [accordLabel, j.accord, accordLabel === "ACCORD" ? "#22d3ee" : "#475569"],
    ["B1 optimiser", j.B1_optimizer, "#f59e0b"],
    ["B0 FCFS", j.B0_fcfs, "#64748b"],
  ];
  const max = Math.max(1, ...rows.map((r) => r[1] ?? 0));
  return (
    <div className="flex flex-col gap-2">
      {rows.map(([name, v, c]) => (
        <div key={name} className="flex items-center gap-3">
          <span className="w-36 text-sm text-slate-300">{name}</span>
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
  const [model, setModel] = useState<string | null>(null);
  useEffect(() => {
    api.health().then((h) => setModel(h.models.ATC ?? null)).catch(() => {});
    api.eval().then((x) => { setR(x); setState("ok"); }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) setState("missing");
      else { setErr(String(e)); setState("error"); }
    });
  }, []);

  if (state === "loading") return <div className="p-6 text-slate-500">loading eval…</div>;
  if (state === "missing") return <div className="p-6 text-2xl text-slate-400">Eval not run yet. Run <span className="font-mono">python -m eval.run_eval</span>.</div>;
  if (state === "error" || !r) return <div className="p-6 text-red-400">{err}</div>;
  const s = r.summary;
  // agents behind the numbers: "live" (Gemini), "mock" (scripted MockLLMClient) or "none" (B0/B1 only)
  const llm = (r.llm ?? s.llm ?? null) as string | null;
  const mock = llm === "mock";
  const none = llm === "none";
  const live = !mock && !none;
  // LLM-dependent tiles: greyed when scripted, "not run" when no agents ran
  const L = <T,>(v: T | null) => (none ? null : v);
  // LLM_ERROR context (display only): rows that never negotiated are still in every rate below
  const nErr = Number(s.n_llm_error ?? 0);
  const nNeg = s.n_negotiated == null ? r.n - nErr : Number(s.n_negotiated);
  const notes = (r as { notes?: unknown }).notes;
  const cons = r.per_scenario.filter((p) => p.final_state === "CONSENSUS");
  const consR2 = cons.filter((p) => p.rounds_used === 2).length;
  const overAll = nErr > 0 ? `over all ${r.n}, incl. ${nErr} LLM_ERROR` : undefined;
  const agents = mock ? "scripted (mock)" : none ? "not run" : `${model ?? "?"} (${llm ?? "live"})`;
  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-baseline gap-3">
        <h1 className="text-3xl font-black">Evaluation</h1>
        {mock ? (
          <span className="rounded bg-amber-600 px-2 py-0.5 text-sm font-bold text-black">SCRIPTED AGENTS (mock): not an LLM result</span>
        ) : none ? (
          <span className="rounded bg-slate-700 px-2 py-0.5 text-sm font-bold text-slate-200">Deterministic baselines only (B0/B1)</span>
        ) : r.measured ? (
          <span className="rounded bg-emerald-800 px-2 py-0.5 text-sm font-bold">MEASURED</span>
        ) : (
          <span className="rounded bg-slate-700 px-2 py-0.5 text-sm font-bold text-slate-300">NOT FULLY MEASURED</span>
        )}
        <span className="text-slate-400">N={r.n} · agents: {agents} · +{r.n_dev} dev · seed {r.seed} · generated {r.generated_at}</span>
      </div>
      {(nErr > 0 || !!notes) && (
        <div className="rounded-lg border border-amber-600 bg-amber-950 px-4 py-3 text-amber-100">
          {nErr > 0 ? (
            <>
              {nNeg} of {r.n} flights negotiated live; {nErr} hit a client bug (LLM_ERROR, fixed in cac78e9) and fell back to the
              optimiser. On the {nNeg} negotiated: {cons.length}/{nNeg} consensus
              {cons.length > 0 && (consR2 === cons.length ? ", all in round 2" : `, ${consR2} in round 2`)}. Rates below are over all {r.n}.
            </>
          ) : (
            (Array.isArray(notes) ? notes : [notes]).map((n, i) => <div key={i}>{String(n)}</div>)
          )}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Tile label="Consensus rate" value={L(pct(s.consensus_rate))} sub={overAll} scripted={mock} />
        <Tile label="Consensus by R2" value={L(pct(s.consensus_by_r2))} scripted={mock} />
        <Tile label="Fallback rate" value={L(pct(s.fallback_rate))} sub={overAll} scripted={mock} />
        <Tile label="Escalate rate" value={L(pct(s.escalate_rate))} scripted={mock} />
        <Tile label="Unsafe proposals blocked" value={L(num(s.unsafe_proposals_blocked, 0))} tone="good" sub="vetoes + rejected counters" scripted={mock} />
        <Tile label="Unsafe plans executed" value={L(num(s.unsafe_plans_executed, 0))} tone={s.unsafe_plans_executed ? "bad" : "good"} sub="must be 0" scripted={mock} />
        <Tile label="Schema failure rate" value={L(pct(s.schema_failure_rate))} scripted={mock} />
        <Tile label="Retry rate" value={L(pct(s.retry_rate))} scripted={mock} />
        <Tile label="Latency p50" value={L(s.latency_p50_ms == null ? null : `${(s.latency_p50_ms / 1000).toFixed(1)} s`)} sub={overAll} scripted={mock} />
        <Tile label="Latency p95" value={L(s.latency_p95_ms == null ? null : `${(s.latency_p95_ms / 1000).toFixed(1)} s`)} scripted={mock} />
        <Tile label="Tokens / resolution" value={L(num(s.tokens_per_resolution, 0))} scripted={mock} />
        <Tile label="Regret vs B1" value={L(num(s.regret_vs_B1_mean, 2))} scripted={mock} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="mb-3 font-semibold text-slate-300">
            Cost J vs baselines{overAll && <span className="ml-2 text-xs font-normal text-slate-500">{overAll}</span>}
          </h2>
          <JBars j={{ ...s.J_mean, accord: L(s.J_mean.accord) }} accordLabel={live ? "ACCORD" : mock ? "ACCORD (scripted)" : "ACCORD (not run)"} />
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
      {r.bad_day && <BadDay b={r.bad_day} />}
      <section className="rounded-lg border border-slate-800">
        <h2 className="border-b border-slate-800 px-3 py-2 font-semibold text-slate-300">Per scenario{mock ? " (scripted agents)" : ""}</h2>
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

type BadDayT = NonNullable<EvalResults["bad_day"]>;

function BadDay({ b }: { b: BadDayT }) {
  // B0/B1 totals: whatever W1 writes (bank delay, misconnects, overtime, J), in a stable order
  const keys = [...new Set([...Object.keys(b.B0 ?? {}), ...Object.keys(b.B1 ?? {})])];
  const v = (side: Record<string, unknown> | null | undefined, k: string) => {
    const x = side?.[k];
    return typeof x === "number" ? (Number.isInteger(x) ? String(x) : x.toFixed(1)) : x == null ? "—" : String(x);
  };
  return (
    <section className="rounded-lg border border-slate-800 p-4">
      <h2 className="font-semibold text-slate-300">Bad-day replay · {b.airport} {b.date} · {b.n_flights} flights</h2>
      <div className="mb-2 text-xs text-slate-500">deterministic baselines only; the LLM negotiation is evaluated on the N set</div>
      <table className="text-sm">
        <thead className="text-xs text-slate-400">
          <tr><th className="pr-6 text-left">total</th><th className="pr-6 text-right">B0 FCFS</th><th className="text-right">B1 optimiser</th></tr>
        </thead>
        <tbody className="font-mono">
          {keys.map((k) => (
            <tr key={k} className="border-t border-slate-800">
              <td className="pr-6 font-sans text-slate-400">{k.replace(/_/g, " ")}</td>
              <td className="pr-6 text-right">{v(b.B0, k)}</td>
              <td className="text-right">{v(b.B1, k)}</td>
            </tr>
          ))}
          <tr className="border-t border-slate-800">
            <td className="pr-6 font-sans text-slate-400">infeasible / escalate</td>
            <td className="pr-6 text-right">{b.b0_infeasible ?? "—"}</td>
            <td className="text-right">{b.b1_escalate ?? "—"}</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}
