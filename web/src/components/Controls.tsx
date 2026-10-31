import { useEffect, useState } from "react";
import type { ScriptedMode } from "../api";
import type { ChaosEvent, ChaosKind, Scenario } from "../types";

const KINDS: ChaosKind[] = ["RUNWAY_CLOSURE", "TAXIWAY_BLOCK", "GATE_FAILURE", "WEATHER_CELL"];

function chaosEvent(kind: ChaosKind, param: string): ChaosEvent {
  switch (kind) {
    case "RUNWAY_CLOSURE":
      return { kind, params: { aar_factor: 0.5 }, note: "one arrival runway closed (AAR x0.5)" };
    case "TAXIWAY_BLOCK":
      return { kind, params: { taxiway: param }, note: `taxiway ${param} blocked` };
    case "GATE_FAILURE":
      return { kind, params: { gate_id: param, duration_min: 90 }, note: `gate ${param} out of service for 90 min` };
    case "WEATHER_CELL":
      return { kind, params: { turbulence_add: 0.3, extra_delay_min: 15 }, note: "convective cell on the arrival path" };
  }
}

/** Popover: pick a chaos kind (+ taxiway/gate from the run's scenario) and inject it. */
export function ChaosMenu({ s, disabled, onInject }: { s: Scenario | null; disabled: boolean; onInject: (ev: ChaosEvent) => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ChaosKind>("TAXIWAY_BLOCK");
  const taxiways = (s?.taxiways ?? []).filter((t) => !s?.blocked_taxiways.includes(t));
  const gates = (s?.gates ?? []).filter((g) => !g.out_of_service).map((g) => g.gate_id);
  const choices = kind === "TAXIWAY_BLOCK" ? taxiways : kind === "GATE_FAILURE" ? gates : [];
  const [param, setParam] = useState("");
  useEffect(() => setParam(choices[0] ?? ""), [kind, s]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative">
      <button disabled={disabled} onClick={() => setOpen(!open)}
        className="rounded border border-amber-600 bg-amber-900 px-3 py-1 font-bold text-amber-100 hover:bg-amber-800 disabled:opacity-40">
        ⚡ Chaos
      </button>
      {open && !disabled && (
        <div className="absolute top-9 left-0 z-[1100] flex w-72 flex-col gap-2 rounded-lg border border-amber-700 bg-slate-900 p-3 shadow-xl">
          {KINDS.map((k) => (
            <label key={k} className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="radio" checked={kind === k} onChange={() => setKind(k)} />
              {k}
            </label>
          ))}
          {choices.length > 0 && (
            <select value={param} onChange={(e) => setParam(e.target.value)} className="rounded border border-slate-700 bg-slate-950 px-2 py-1">
              {choices.map((c) => (
                <option key={c} value={c}>
                  {kind === "TAXIWAY_BLOCK" ? `taxiway ${c}` : `gate ${c}${c === s?.planned_gate ? " (planned)" : ""}`}
                </option>
              ))}
            </select>
          )}
          <div className="text-xs text-slate-400">{chaosEvent(kind, param).note}</div>
          <button
            onClick={() => {
              onInject(chaosEvent(kind, param));
              setOpen(false);
            }}
            disabled={choices.length === 0 && (kind === "TAXIWAY_BLOCK" || kind === "GATE_FAILURE")}
            className="rounded bg-amber-600 px-3 py-1 font-bold hover:bg-amber-500 disabled:opacity-40">
            Inject &amp; re-negotiate
          </button>
        </div>
      )}
    </div>
  );
}

const MODES: { mode: ScriptedMode; label: string }[] = [
  { mode: "deadlock", label: "Deadlock → fallback" },
  { mode: "unsafe", label: "Unsafe agreement → veto" },
  { mode: "hallucinate", label: "Hallucinated citation → REJECT" },
];

/** "Demo scenarios" (scripted failures) + recorded replays. */
export function DemoMenu({ disabled, replays, onMode, onReplay }: {
  disabled: boolean; replays: string[]; onMode: (m: ScriptedMode) => void; onReplay: (name: string) => void;
}) {
  return (
    <select value="" disabled={disabled}
      onChange={(e) => {
        const v = e.target.value;
        if (v.startsWith("replay:")) onReplay(v.slice(7));
        else if (v) onMode(v as ScriptedMode);
      }}
      className="rounded border border-slate-600 bg-slate-900 px-2 py-1 disabled:opacity-40">
      <option value="">Demo scenarios…</option>
      <optgroup label="Scripted failures (mock agents)">
        {MODES.map((m) => (
          <option key={m.mode} value={m.mode}>{m.label}</option>
        ))}
      </optgroup>
      {replays.length > 0 && (
        <optgroup label="Recorded replays">
          {replays.map((r) => (
            <option key={r} value={`replay:${r}`}>▶ replay {r}</option>
          ))}
        </optgroup>
      )}
    </select>
  );
}
