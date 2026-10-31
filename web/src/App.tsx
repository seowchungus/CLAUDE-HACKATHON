import { useEffect, useState } from "react";
import { api } from "./api";
import { DecisionPanel } from "./components/DecisionPanel";
import { NegotiationRoom } from "./components/NegotiationRoom";
import { ConstraintWall } from "./components/ConstraintWall";
import { Gantt } from "./components/Gantt";
import { ChainBadge, LogDrawer, useChain } from "./components/LogDrawer";
import { RoundTracker } from "./components/RoundTracker";
import { ScenarioBar } from "./components/ScenarioBar";
import { TrafficMap } from "./components/TrafficMap";
import type { ChaosEvent, ChaosKind, ScenarioResponse, ScenarioSummary } from "./types";
import { decidedPlan, useRunStream } from "./useRunStream";

const CHAOS: Record<ChaosKind, ChaosEvent> = {
  RUNWAY_CLOSURE: { kind: "RUNWAY_CLOSURE", params: { aar_factor: 0.5 }, note: "one runway closed" },
  TAXIWAY_BLOCK: { kind: "TAXIWAY_BLOCK", params: { taxiway: "B" }, note: "taxiway B blocked" },
  GATE_FAILURE: { kind: "GATE_FAILURE", params: { gate_id: "A3", duration_min: 90 }, note: "gate A3 jet bridge failure" },
  WEATHER_CELL: { kind: "WEATHER_CELL", params: { turbulence_add: 0.3, extra_delay_min: 15 }, note: "convective cell on arrival path" },
};

export const Panel = ({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) => (
  <section className={`rounded-lg border border-slate-800 bg-slate-950 ${className}`}>
    <h2 className="border-b border-slate-800 px-3 py-1.5 text-xs font-semibold tracking-widest text-slate-400 uppercase">{title}</h2>
    {children}
  </section>
);

export default function App() {
  const [list, setList] = useState<ScenarioSummary[]>([]);
  const [sid, setSid] = useState<string>("");
  const [sc, setSc] = useState<ScenarioResponse | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [llmOn, setLlmOn] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [logOpen, setLogOpen] = useState(() => new URLSearchParams(location.search).has("log"));
  const st = useRunStream(runId);
  const chain = useChain(runId, `${!!st.ended}-${!!st.approved}-${logOpen}`);

  useEffect(() => {
    api.scenarios().then((l) => {
      setList(l);
      if (l.length) setSid(l[0].scenario_id);
    }).catch((e) => setErr(String(e)));
    api.health().then((h) => setLlmOn(h.llm_enabled)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sid) return;
    setSc(null);
    api.scenario(sid).then(setSc).catch((e) => setErr(String(e)));
    // ?autorun=1 starts a run on load (demo/headless checks)
    if (new URLSearchParams(location.search).has("autorun") && !runId)
      api.createRun(sid).then((r) => setRunId(r.run_id)).catch((e) => setErr(String(e)));
  }, [sid]);

  const plan = decidedPlan(st);
  const tentOpt = st.options.find((o) => o.option_id === st.tentative?.option_id) ?? null;

  const run = async () => {
    setErr(null);
    try {
      setRunId((await api.createRun(sid)).run_id);
    } catch (e) {
      setErr(String(e));
    }
  };
  const chaos = async (k: ChaosKind) => {
    if (!runId) return;
    try {
      setRunId((await api.chaos(runId, CHAOS[k])).run_id);
    } catch (e) {
      setErr(String(e));
    }
  };
  const toggleKill = async () => {
    try {
      setLlmOn((await api.kill(!llmOn)).llm_enabled);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b border-slate-800 px-4 py-2">
        <span className="text-xl font-black tracking-widest text-sky-400">ACCORD</span>
        <span className="text-sm text-slate-500">ops console</span>
        <select value={sid} onChange={(e) => setSid(e.target.value)} className="ml-4 rounded border border-slate-700 bg-slate-900 px-2 py-1">
          {list.map((s) => (
            <option key={s.scenario_id} value={s.scenario_id}>
              {s.flight_id} {s.origin}→{s.destination} {s.date} {s.disruption_type} {s.disruption_min}m
            </option>
          ))}
        </select>
        <button onClick={run} disabled={!sid} className="rounded bg-sky-600 px-4 py-1 font-bold hover:bg-sky-500 disabled:opacity-40">
          ▶ Run
        </button>
        <select
          value=""
          disabled={!runId}
          onChange={(e) => e.target.value && chaos(e.target.value as ChaosKind)}
          className="rounded border border-amber-700 bg-amber-950 px-2 py-1 text-amber-200 disabled:opacity-40"
        >
          <option value="">⚡ Chaos…</option>
          {Object.keys(CHAOS).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <button
          onClick={toggleKill}
          className={`rounded px-3 py-1 font-bold ${llmOn ? "bg-slate-800 text-slate-200 hover:bg-slate-700" : "bg-red-700 text-white"}`}
        >
          {llmOn ? "LLM ON · kill" : "LLM KILLED · restore"}
        </button>
        <button
          onClick={() => setLogOpen(true)}
          disabled={!runId}
          className="flex items-center gap-2 rounded bg-slate-800 px-3 py-1 font-semibold hover:bg-slate-700 disabled:opacity-40"
        >
          Log <ChainBadge v={chain.verify} />
        </button>
        <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
          {st.started?.parent_run_id && <span className="text-amber-400">re-run of {st.started.parent_run_id}</span>}
          {runId && <span className="font-mono">{runId}</span>}
          {runId && <span className={st.connected ? "text-emerald-400" : "text-slate-600"}>● {st.connected ? "live" : "idle"}</span>}
        </div>
      </header>
      {sc && <ScenarioBar s={sc.bundle.scenario} />}
      {st.started && st.started.chaos_applied.length > 0 && (
        <div className="border-b border-amber-700 bg-amber-950 px-4 py-1 text-amber-200">
          ⚡ chaos applied: {st.started.chaos_applied.map((c) => `${c.kind} ${c.note}`).join(" · ")}
        </div>
      )}
      {err && <div className="bg-red-950 px-4 py-1 text-sm text-red-300">{err}</div>}
      {st.errors.map((e, i) => (
        <div key={i} className="bg-red-950 px-4 py-1 text-sm text-red-300">{e}</div>
      ))}
      <RoundTracker st={st} />
      <main className="grid flex-1 grid-cols-12 gap-3 px-4 pb-4">
        <Panel title="Negotiation room" className="col-span-8 p-3">
          <NegotiationRoom st={st} />
        </Panel>
        <div className="col-span-4 flex flex-col gap-3">
          <Panel title="Traffic map">
            {sc ? (
              <TrafficMap map={sc.map} etaNew={plan?.metrics.eta_new_min ?? null} chaos={(st.started?.chaos_applied.length ?? 0) > 0} />
            ) : (
              <div className="p-4 text-slate-600">loading…</div>
            )}
          </Panel>
          <Panel title="Runway & gates">
            {sc && <Gantt s={sc.bundle.scenario} opt={plan ?? tentOpt} isPlan={!!plan} />}
          </Panel>
        </div>
        <Panel title="Decision" className="col-span-5">
          <DecisionPanel st={st} />
        </Panel>
        <Panel title="Constraint wall" className="col-span-7">
          {sc && (
            <ConstraintWall
              st={st}
              options={st.options.length ? st.options : sc.bundle.options}
              checks={Object.keys(st.checks).length ? st.checks : sc.bundle.checks}
              fcfs={st.fcfs ?? sc.bundle.fcfs}
              fallbackId={(st.fallbackShadow ?? sc.bundle.fallback).option_id}
            />
          )}
        </Panel>
      </main>
      {logOpen && runId && <LogDrawer runId={runId} entries={chain.entries} verify={chain.verify} onClose={() => setLogOpen(false)} />}
    </div>
  );
}
