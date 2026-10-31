import { useEffect, useState } from "react";
import { api } from "../api";
import type { AirportLimits, ConstraintId, Health, Limits } from "../types";

/** Where each hard constraint's limit comes from (organisers' workbook vs our own rule). */
export const C_SOURCE: Record<ConstraintId, { src: "workbook" | "ours"; note: string }> = {
  H1_wake_separation: { src: "workbook", note: "wake_separation min_time_s (departure times applied to arrivals)" },
  H2_runway_capacity: { src: "workbook", note: "max_runway_ops_per_hour × 50% arrival share (share + weather factor are ours)" },
  H3_fuel_reserve: { src: "workbook", note: "fuel_and_crew: 30 min final reserve" },
  H4_gate_validity: { src: "workbook", note: "gates, spare gates, min turnaround, 20-min gate-change notice" },
  H5_crew_duty: { src: "workbook", note: "fuel_and_crew: flight crew 13 h duty" },
  H6_taxiway_reachability: { src: "ours", note: "taxiway graph is synthetic; workbook silent" },
  H7_severe_turbulence: { src: "ours", note: "severe threshold is ours; workbook silent" },
};

const label = (k: string) => k.replace(/_/g, " ").replace(/\bmin\b/, "(min)").replace(/\bs$/, "(s)");
const val = (v: unknown) => (v == null ? "—" : typeof v === "object" ? JSON.stringify(v).replace(/[{}"]/g, "").replace(/,/g, ", ") : String(v));

/** Collapsible "Challenge limits" panel: the destination's workbook row, wake table, fuel/crew, rules, and our deviations. */
export function LimitsPanel({ scenarioId, airport: scAirport, dest }: { scenarioId: string; airport?: AirportLimits | Record<string, never>; dest?: string }) {
  const [lim, setLim] = useState<Limits | null>(null);
  const [open, setOpen] = useState(true);
  useEffect(() => {
    if (!scenarioId) return;
    api.limits(scenarioId).then(setLim).catch(() => setLim(null));
  }, [scenarioId]);
  if (!lim) return null;
  // the run's own scenario carries its airport row (v1.2); fall back to the server's table lookup
  const ap = scAirport && Object.keys(scAirport).length ? (scAirport as AirportLimits) : lim.airport;
  const wake = lim.workbook.wake_separation;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 border-b border-slate-800 px-3 py-1.5 text-left text-xs font-semibold tracking-widest text-slate-400 uppercase">
        <span>{open ? "▾" : "▸"}</span> Challenge limits
        <span className="font-normal tracking-normal normal-case text-slate-500">organisers' workbook · {lim.deviations.length} deviations</span>
      </button>
      {open && (
        <div className="grid grid-cols-1 gap-3 p-3 text-xs md:grid-cols-3">
          <div>
            <h3 className="mb-1 font-semibold text-slate-300">Airport {dest ?? ""} <span className="font-normal text-slate-500">(workbook row)</span></h3>
            {ap ? (
              <table className="w-full">
                <tbody>
                  {(["size_class", "active_runways", "max_runway_ops_per_hour", "gates", "spare_gates_at_any_time", "min_turnaround_min"] as const).map((k) => (
                    <tr key={k} className="border-t border-slate-900">
                      <td className="py-0.5 text-slate-400">{label(k)}</td>
                      <td className="text-right font-mono text-slate-100">{val(ap[k])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-slate-600">no workbook row for this scenario (fixture)</div>
            )}
            <h3 className="mt-2 mb-1 font-semibold text-slate-300">Wake separation (s)</h3>
            <div className="grid grid-cols-3 gap-x-2 font-mono">
              {Object.entries(wake).map(([k, v]) => (
                <span key={k}><span className="text-slate-500">{k}</span> {v}</span>
              ))}
            </div>
          </div>
          <div>
            <h3 className="mb-1 font-semibold text-slate-300">Fuel & crew</h3>
            <table className="w-full">
              <tbody>
                {Object.entries({ ...lim.workbook.fuel_and_crew, ...lim.workbook.rules_of_play }).map(([k, v]) => (
                  <tr key={k} className="border-t border-slate-900">
                    <td className="py-0.5 text-slate-400">{label(k)}</td>
                    <td className="text-right font-mono text-slate-100">{val(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="rounded border border-amber-700 bg-amber-950/50 p-2">
            <h3 className="mb-1 font-bold text-amber-300">Deviations from the workbook</h3>
            <ul className="list-disc space-y-1 pl-4 text-amber-100">
              {lim.deviations.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}

export function budgetTotals(h: Health | null) {
  const b = h?.llm_budget;
  if (!b) return null;
  const ks = Object.values(b.keys);
  if (!ks.length) return null;
  // headline = the key with the most headroom (the one the next call will use); pinned/exhausted keys only show in the tooltip
  const best = ks.reduce((a, k) => (k.remaining > a.remaining ? k : a));
  const remaining = ks.reduce((a, k) => a + Math.max(0, k.remaining), 0);
  return { b, used: best.used_today, cap: best.cap, remaining, exhausted: b.enforce && remaining <= 0 };
}

/** Header meter: "Flash-Lite 223/480 today". Hidden when the server reports no budget. */
export function BudgetMeter({ health }: { health: Health | null }) {
  const t = budgetTotals(health);
  if (!t) return null;
  const frac = t.cap ? t.used / t.cap : 1;
  const tone = t.exhausted || frac >= 1 ? "bg-red-600" : frac > 0.8 ? "bg-amber-500" : "bg-emerald-500";
  const text = t.exhausted || frac >= 1 ? "text-red-300" : frac > 0.8 ? "text-amber-300" : "text-slate-300";
  const model = (health?.models.ATC ?? "").replace(/^gemini-[\d.]+-/, "").replace(/(^|-)(\w)/g, (_, d, c) => d + c.toUpperCase());
  const keys = Object.entries(t.b.keys);
  const tip = [
    "free tier 500/day per project, 20 reserved",
    ...keys.map(([n, k]) => `${n}: ${k.used_today}/${k.cap} (rpm ${k.rpm_cap})`),
    `resets ${new Date(t.b.resets_at).toLocaleTimeString()}`,
    t.b.enforce ? "hard guard ON" : "guard OFF",
  ].join("\n");
  return (
    <span title={tip} className={`flex cursor-help items-center gap-1.5 text-xs ${text}`}>
      {model || "LLM"} {t.used}/{t.cap} today{t.remaining > t.cap - t.used ? ` (+${t.remaining - (t.cap - t.used)} on other keys)` : ""}
      <span className="h-2 w-16 overflow-hidden rounded bg-slate-800">
        <span className={`block h-2 ${tone}`} style={{ width: `${Math.min(100, frac * 100)}%` }} />
      </span>
    </span>
  );
}
