import type { CheckReport, Option } from "../types";
import { CONSTRAINTS, shortC } from "../types";
import { decidedPlan, type RunState } from "../useRunStream";

interface Props {
  st: RunState;
  options: Option[];
  checks: Record<string, CheckReport>;
  fcfs: Option | null;
  fallbackId: string | null;
}

export function ConstraintWall({ st, options, checks, fcfs, fallbackId }: Props) {
  const planId = decidedPlan(st)?.option_id ?? null;
  const tentId = st.tentative?.option_id ?? null;
  const rows = fcfs ? [...options, fcfs] : options;
  return (
    <div className="overflow-x-auto p-2">
      <table className="w-full border-separate border-spacing-0.5 text-sm">
        <thead>
          <tr className="text-xs text-slate-400">
            <th className="px-2 text-left">option</th>
            {CONSTRAINTS.map((c) => (
              <th key={c} className="px-1" title={c}>
                {shortC(c)}
                <div className="text-[9px] font-normal text-slate-500">{c.split("_").slice(1).join(" ")}</div>
              </th>
            ))}
            <th className="px-2 text-right">J</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => {
            const id = o.option_id;
            const isB0 = o.source === "fcfs";
            const rep = checks[id];
            const rowCls = [
              isB0 ? "opacity-45" : "",
              id === planId ? "outline-2 outline-emerald-400 bg-emerald-950/60" : id === tentId ? "outline-2 outline-dashed outline-sky-400" : "",
              st.newOptionIds.includes(id) ? "flash" : "",
            ].join(" ");
            return (
              <tr key={`${id}-${st.newOptionIds.includes(id)}`} className={rowCls}>
                <td className="px-2 py-1 whitespace-nowrap">
                  <span className="font-mono font-semibold">{id}</span>
                  {isB0 && <span className="ml-1 rounded bg-slate-700 px-1 text-[10px]">B0</span>}
                  {id === fallbackId && <span className="ml-1 rounded bg-amber-700 px-1 text-[10px]">B1</span>}
                  {o.source === "counter" && <span className="ml-1 rounded bg-violet-800 px-1 text-[10px]">counter·{o.proposed_by}</span>}
                  {id === planId && <span className="ml-1 rounded bg-emerald-700 px-1 text-[10px]">PLAN</span>}
                  <div className="text-[11px] text-slate-400">{o.label}</div>
                </td>
                {CONSTRAINTS.map((c) => {
                  const r = rep?.results.find((x) => x.constraint_id === c);
                  if (!r) return <td key={c} className="bg-slate-800 text-center text-slate-500">·</td>;
                  return (
                    <td
                      key={c}
                      title={`${c}: ${r.detail}`}
                      className={`cursor-help text-center font-bold ${r.passed ? "bg-emerald-800/80 text-emerald-100" : "bg-red-700 text-white"}`}
                    >
                      {r.passed ? "✓" : "✗"}
                    </td>
                  );
                })}
                <td className="px-2 text-right font-mono text-slate-300">{o.metrics.cost_J}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-1 text-[11px] text-slate-500">
        Hover a cell for the checker's detail. B0 = first-come-first-served baseline (not a candidate) · B1 = deterministic fallback choice (min J).
      </div>
    </div>
  );
}
