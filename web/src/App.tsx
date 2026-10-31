import { useCallback, useEffect, useState } from "react";
import { api, type ScriptedMode } from "./api";
import { ConstraintWall } from "./components/ConstraintWall";
import { ChaosMenu, DemoMenu } from "./components/Controls";
import { DecisionPanel } from "./components/DecisionPanel";
import { EvalPage } from "./components/EvalPage";
import { Gantt } from "./components/Gantt";
import { ChainBadge, LogDrawer, useChain } from "./components/LogDrawer";
import { NegotiationRoom } from "./components/NegotiationRoom";
import { RoundTracker } from "./components/RoundTracker";
import { ScenarioBar } from "./components/ScenarioBar";
import { TrafficMap } from "./components/TrafficMap";
import type { ChaosEvent, Health, ScenarioResponse, ScenarioSummary } from "./types";
import { decidedPlan, useRunStream } from "./useRunStream";

export const Panel = ({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) => (
  <section className={`rounded-lg border border-slate-800 bg-slate-950 ${className}`}>
    <h2 className="border-b border-slate-800 px-3 py-1.5 text-xs font-semibold tracking-widest text-slate-400 uppercase">{title}</h2>
    {children}
  </section>
);

const params = new URLSearchParams(location.search);

export default function App() {
  const [view, setView] = useState<"console" | "eval">(params.has("eval") ? "eval" : "console");
  const [list, setList] = useState<ScenarioSummary[]>([]);
  const [sid, setSid] = useState<string>("");
  const [sc, setSc] = useState<ScenarioResponse | null>(null);
  const [streamKey, setStreamKey] = useState<string | null>(params.get("replay") ? `replay:${params.get("replay")}` : null);
  const [health, setHealth] = useState<Health | null>(null);
  const [replays, setReplays] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [reqMode, setReqMode] = useState<ScriptedMode | null>(null);
  const [logOpen, setLogOpen] = useState(() => params.has("log"));
  const st = useRunStream(streamKey);
  const runId = st.replay ? null : st.runId;
  const chain = useChain(runId, `${!!st.ended}-${!!st.approved}-${logOpen}`);
  const fail = (e: unknown) => setErr(e instanceof Error ? e.message : String(e));

  const refreshHealth = useCallback(() => api.health().then(setHealth).catch(() => setHealth(null)), []);
  useEffect(() => {
    api.scenarios().then((l) => {
      setList(l);
      if (l.length) setSid(l[0].scenario_id);
    }).catch(fail);
    api.replays().then(setReplays).catch(() => {});
    refreshHealth();
    const t = setInterval(refreshHealth, 10000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  // Scenario view: the picked scenario before a run; the run's own (possibly chaos-mutated) bundle once a run exists.
  useEffect(() => {
    if (!sid || runId) return;
    setSc(null);
    api.scenario(sid).then(setSc).catch(fail);
  }, [sid, runId]);
  useEffect(() => {
    if (!runId) return;
    api.runBundle(runId).then(setSc).catch(fail);
  }, [runId]);
  useEffect(() => {
    // replay: show the scenario the recording was made on
    if (st.replay && st.started?.scenario_id) api.scenario(st.started.scenario_id).then(setSc).catch(() => {});
  }, [st.replay, st.started?.scenario_id]);

  const start = async (mode?: ScriptedMode) => {
    setErr(null);
    try {
      setStreamKey((await api.createRun(sid, mode)).run_id);
      setReqMode(mode ?? null);
    } catch (e) {
      fail(e);
    }
  };
  useEffect(() => {
    // ?autorun=1 starts a run on load (demo/headless checks); ?mode=deadlock etc. for scripted runs
    if (sid && params.has("autorun") && !streamKey) start((params.get("mode") as ScriptedMode) ?? undefined);
  }, [sid]); // eslint-disable-line react-hooks/exhaustive-deps

  const chaos = async (ev: ChaosEvent) => {
    if (!runId) return;
    try {
      setStreamKey((await api.chaos(runId, ev)).run_id);
    } catch (e) {
      fail(e);
    }
  };
  const toggleKill = async () => {
    try {
      await api.kill(!(health?.llm_enabled ?? true));
      await refreshHealth();
    } catch (e) {
      fail(e);
    }
  };

  const llmOn = health?.llm_enabled ?? true;
  const plan = decidedPlan(st);
  const tentOpt = st.options.find((o) => o.option_id === st.tentative?.option_id) ?? null;
  const chaosOn = (st.started?.chaos_applied.length ?? 0) > 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-2">
        <span className="text-xl font-black tracking-widest text-sky-400">ACCORD</span>
        <div className="flex overflow-hidden rounded border border-slate-700 text-sm">
          {(["console", "eval"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} className={`px-3 py-1 ${view === v ? "bg-slate-700 font-bold" : "hover:bg-slate-800"}`}>
              {v === "console" ? "Console" : "Eval"}
            </button>
          ))}
        </div>
        {view === "console" && (
          <>
            <select value={sid} onChange={(e) => { setSid(e.target.value); setStreamKey(null); }}
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1">
              {list.map((s) => (
                <option key={s.scenario_id} value={s.scenario_id}>
                  {s.flight_id} {s.origin}→{s.destination} {s.date} {s.disruption_type} {s.disruption_min}m
                </option>
              ))}
            </select>
            <button onClick={() => start()} disabled={!sid} className="rounded bg-sky-600 px-4 py-1 font-bold hover:bg-sky-500 disabled:opacity-40">
              ▶ Run
            </button>
            <ChaosMenu s={sc?.bundle.scenario ?? null} disabled={!runId} onInject={chaos} />
            <button onClick={toggleKill} title="Simulate an LLM outage: the deterministic fallback takes over"
              className={`rounded px-4 py-1 text-base font-black ${llmOn ? "border border-red-700 bg-slate-900 text-red-300 hover:bg-red-950" : "animate-pulse bg-red-600 text-white"}`}>
              {llmOn ? "☠ Kill the LLM" : "LLM OFF · restore"}
            </button>
            <DemoMenu disabled={!sid} replays={replays} onMode={start} onReplay={(n) => setStreamKey(`replay:${n}`)} />
            <button onClick={() => setLogOpen(true)} disabled={!runId}
              className="flex items-center gap-2 rounded bg-slate-800 px-3 py-1 font-semibold hover:bg-slate-700 disabled:opacity-40">
              Log <ChainBadge v={chain.verify} />
            </button>
          </>
        )}
        <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
          <span className={llmOn ? "text-emerald-400" : "font-bold text-red-400"}>LLM {llmOn ? "enabled" : "disabled"}</span>
          {st.started?.parent_run_id && <span className="text-amber-400">re-run of {st.started.parent_run_id}</span>}
          {st.runId && <span className="font-mono">{st.runId}</span>}
          {streamKey && <span className={st.connected ? "text-emerald-400" : "text-slate-600"}>● {st.connected ? "live" : "idle"}</span>}
        </div>
      </header>
      {view === "eval" ? (
        <EvalPage />
      ) : (
        <>
          {(st.replay || st.started?.scripted) && (
            <div className="flex gap-3 border-b border-slate-800 bg-slate-900 px-4 py-1 text-sm">
              {st.replay && (
                <span className="rounded bg-orange-700 px-2 font-bold text-white">
                  REPLAY ({st.replay.name}, recorded {st.replay.recordedAt ? new Date(st.replay.recordedAt).toISOString().replace("T", " ").slice(0, 19) + " UTC" : "…"})
                </span>
              )}
              {st.started?.scripted && (
                <span className="rounded bg-fuchsia-700 px-2 font-bold text-white">SCRIPTED{(st.started.mode ?? reqMode) ? `: ${st.started.mode ?? reqMode}` : ""} (mock agents)</span>
              )}
            </div>
          )}
          {sc && <ScenarioBar s={sc.bundle.scenario} />}
          {chaosOn && (
            <div className="border-b border-amber-700 bg-amber-950 px-4 py-1 text-amber-200">
              ⚡ chaos applied: {st.started!.chaos_applied.map((c) => `${c.kind}${c.note ? ` (${c.note})` : ""}`).join(" · ")}
            </div>
          )}
          {err && (
            <div className="flex bg-red-950 px-4 py-1 text-sm text-red-300">
              {err}
              <button className="ml-auto" onClick={() => setErr(null)}>×</button>
            </div>
          )}
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
                {sc ? <TrafficMap map={sc.map} etaNew={plan?.metrics.eta_new_min ?? null} chaos={chaosOn} /> : <div className="p-4 text-slate-600">loading…</div>}
              </Panel>
              <Panel title="Runway & gates">{sc && <Gantt s={sc.bundle.scenario} opt={plan ?? tentOpt} isPlan={!!plan} />}</Panel>
            </div>
            <Panel title="Decision" className="col-span-5">
              <DecisionPanel st={st} onSigned={() => chain.refresh()} />
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
        </>
      )}
    </div>
  );
}
