import { useState } from "react";
import { api } from "../api";
import { hhmm, shortC } from "../types";
import { decidedPlan, type RunState } from "../useRunStream";

export function DecisionPanel({ st }: { st: RunState }) {
  const plan = decidedPlan(st);
  const [overrideId, setOverrideId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const source = st.awaiting?.decision_source ?? (st.consensus ? "CONSENSUS" : st.fallback ? "FALLBACK" : null);
  if (!source) return <div className="p-4 text-slate-500">No decision yet. The plan appears here after consensus or fallback.</div>;

  const check = st.consensus?.check ?? (plan ? st.checks[plan.option_id] : undefined);
  const send = async (action: "APPROVE" | "OVERRIDE") => {
    if (!st.runId) return;
    const option_id = action === "APPROVE" ? (plan?.option_id ?? "") : overrideId;
    if (!option_id) return setErr("pick an option to override with");
    setBusy(true);
    setErr(null);
    try {
      await api.approve(st.runId, action, option_id, "duty_manager", action === "OVERRIDE" ? "manual override" : "");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const srcCls = source === "CONSENSUS" ? "bg-emerald-700" : source === "FALLBACK" ? "bg-amber-700" : "bg-red-700";
  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-3">
        <span className={`rounded px-3 py-1 text-lg font-black ${srcCls}`}>{source}</span>
        {st.awaiting && <span className="text-slate-400">rounds used: {st.awaiting.rounds_used}</span>}
        {st.fallback && <span className="text-sm text-slate-400">reason: {st.fallback.reason} · {st.fallback.result.reason}</span>}
      </div>
      {plan ? (
        <div>
          <div className="text-2xl font-bold">
            <span className="font-mono text-sky-300">{plan.option_id}</span> {plan.label}
          </div>
          <div className="mt-1 grid grid-cols-4 gap-x-4 gap-y-1 text-sm text-slate-300">
            <span>ETA {hhmm(plan.metrics.eta_new_min)}</span>
            <span>runway {hhmm(plan.metrics.runway_slot_min)}</span>
            <span>gate {plan.metrics.gate}</span>
            <span>fuel @ land {plan.metrics.fuel_at_landing_min} min</span>
            <span>misconnects {plan.metrics.misconnected_pax}</span>
            <span>ramp OT {plan.metrics.ramp_overtime_min} min</span>
            <span>bank delay +{plan.metrics.bank_delay_added_min} min</span>
            <span>J = {plan.metrics.cost_J}</span>
          </div>
          {check && (
            <div className="mt-2 flex flex-wrap gap-1">
              {check.results.map((r) => (
                <span key={r.constraint_id} title={r.detail} className={`rounded px-1.5 py-0.5 font-mono text-xs ${r.passed ? "bg-emerald-900 text-emerald-200" : "bg-red-900 text-red-200"}`}>
                  {shortC(r.constraint_id)} {r.passed ? "✓" : "✗"}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-2xl font-bold text-red-400">ESCALATE: no safe automated plan</div>
      )}
      {st.consensus && (
        <div className="grid grid-cols-3 gap-2 text-sm">
          {Object.entries(st.consensus.accepts).map(([role, why]) => (
            <div key={role} className="rounded bg-slate-900 p-2">
              <span className="font-bold">{role}</span> <span className="text-slate-300">{why}</span>
            </div>
          ))}
        </div>
      )}
      {st.narration && <p className="rounded border border-slate-700 bg-slate-900 p-3 text-slate-200">{st.narration}</p>}
      {st.approved ? (
        <div className="rounded border border-emerald-600 bg-emerald-950 p-3 text-lg font-semibold text-emerald-200">
          ✓ {st.approved.action} by {st.approved.by} → <span className="font-mono">{st.approved.option_id}</span>
          <div className="font-mono text-xs text-emerald-400">final hash {st.approved.final_hash}</div>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button disabled={busy || !plan} onClick={() => send("APPROVE")} className="rounded bg-emerald-600 px-5 py-2 text-lg font-bold hover:bg-emerald-500 disabled:opacity-40">
            Approve
          </button>
          <select value={overrideId} onChange={(e) => setOverrideId(e.target.value)} className="rounded border border-slate-700 bg-slate-900 px-2 py-2">
            <option value="">override with…</option>
            {st.options.map((o) => (
              <option key={o.option_id} value={o.option_id}>
                {o.option_id} {st.checks[o.option_id]?.feasible === false ? "(infeasible)" : ""}
              </option>
            ))}
          </select>
          <button disabled={busy} onClick={() => send("OVERRIDE")} className="rounded bg-slate-700 px-4 py-2 font-semibold hover:bg-slate-600 disabled:opacity-40">
            Override
          </button>
          {err && <span className="text-sm text-red-400">{err}</span>}
        </div>
      )}
    </div>
  );
}
