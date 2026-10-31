import { useEffect, useState } from "react";
import { api } from "../api";
import type { Option } from "../types";
import { hhmm, shortC } from "../types";
import { decidedPlan, type RunState } from "../useRunStream";

export function GateChangeBadge({ o }: { o: Option }) {
  if (!o.metrics.gate_change) return null;
  const n = o.metrics.gate_change_notice_min;
  const ok = n != null && n >= 20;
  return (
    <span className={`ml-1 rounded px-1 text-[10px] font-bold ${ok ? "bg-sky-800 text-sky-100" : "bg-red-700 text-white"}`}
      title="gate change; workbook requires >= 20 min notice before arrival">
      GATE CHANGE {n != null ? `${n} min notice` : ""}
    </span>
  );
}

export const fuelText = (o: Option) =>
  `${o.metrics.fuel_at_landing_min} min${o.metrics.fuel_at_landing_kg != null ? ` (${Math.round(o.metrics.fuel_at_landing_kg)} kg)` : ""}`;

export function DecisionPanel({ st, onSigned }: { st: RunState; onSigned?: () => void }) {
  const plan = decidedPlan(st);
  const [overrideId, setOverrideId] = useState("");
  const [by, setBy] = useState("duty manager");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [signed, setSigned] = useState<{ action: string; option_id: string; final_hash: string } | null>(null);

  useEffect(() => {
    setSigned(null);
    setErr(null);
    setOverrideId("");
    setNote("");
  }, [st.runId]);

  const source = st.awaiting?.decision_source ?? (st.consensus ? "CONSENSUS" : st.fallback ? "FALLBACK" : null);
  if (st.ended?.final_state === "SUPERSEDED")
    return <div className="p-4 text-slate-400">This run was superseded by a chaos re-negotiation.</div>;
  if (!source) return <div className="p-4 text-slate-500">No decision yet. The plan appears here after consensus or fallback.</div>;

  const escalate = source === "ESCALATE";
  const check = st.consensus?.check ?? (plan ? st.checks[plan.option_id] : undefined);
  const canSign = !!st.awaiting && !st.replay && !signed && !st.approved;

  const send = async (action: "APPROVE" | "OVERRIDE") => {
    if (!st.runId) return;
    const option_id = action === "APPROVE" ? (plan?.option_id ?? "") : overrideId;
    if (!option_id) return setErr("pick an option to override with");
    setBusy(true);
    setErr(null);
    try {
      const r = await api.approve(st.runId, action, option_id, by || "duty manager", note);
      setSigned({ action, option_id, final_hash: r.final_hash });
      onSigned?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const srcCls = source === "CONSENSUS" ? "bg-emerald-700" : source === "FALLBACK" ? "bg-amber-700" : "bg-red-700";
  const shown = signed ?? (st.approved ? { action: st.approved.action, option_id: st.approved.option_id, final_hash: st.approved.final_hash } : null);
  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded px-3 py-1 text-lg font-black ${srcCls}`}>{source}</span>
        {st.awaiting && <span className="text-slate-400">rounds used: {st.awaiting.rounds_used}</span>}
        {st.fallback && <span className="text-sm text-slate-400">reason: {st.fallback.reason} · {st.fallback.result.reason}</span>}
      </div>
      {plan ? (
        <div>
          <div className="text-2xl font-bold">
            <span className="font-mono text-sky-300">{plan.option_id}</span> {plan.label}
            <GateChangeBadge o={plan} />
          </div>
          <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-slate-300 xl:grid-cols-4">
            <span>ETA {hhmm(plan.metrics.eta_new_min)}</span>
            <span>runway {hhmm(plan.metrics.runway_slot_min)}</span>
            <span>gate {plan.metrics.gate}</span>
            <span>fuel @ land {fuelText(plan)}</span>
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
        <div className="text-2xl font-bold text-red-400">ESCALATE: no safe automated plan. A human must choose (Override).</div>
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
      {shown ? (
        <div className="rounded border border-emerald-600 bg-emerald-950 p-3 text-lg font-semibold text-emerald-200">
          ✓ Signed: {shown.action} <span className="font-mono">{shown.option_id}</span> · chain head{" "}
          <span className="font-mono" title={shown.final_hash}>{shown.final_hash.slice(0, 12)}…</span>
        </div>
      ) : canSign ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <input value={by} onChange={(e) => setBy(e.target.value)} placeholder="signed by" className="w-40 rounded border border-slate-700 bg-slate-900 px-2 py-2" />
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note (optional)" className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-2" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button disabled={busy || !plan || escalate} onClick={() => send("APPROVE")}
              className="rounded bg-emerald-600 px-5 py-2 text-lg font-bold hover:bg-emerald-500 disabled:opacity-40">
              Approve
            </button>
            <select value={overrideId} onChange={(e) => setOverrideId(e.target.value)} className="rounded border border-slate-700 bg-slate-900 px-2 py-2">
              <option value="">override with…</option>
              {st.options.map((o) => (
                <option key={o.option_id} value={o.option_id}>
                  {o.option_id} {o.label} {st.checks[o.option_id]?.feasible === false ? "(fails checker)" : ""}
                </option>
              ))}
            </select>
            <button disabled={busy || !overrideId} onClick={() => send("OVERRIDE")}
              className="rounded bg-slate-700 px-4 py-2 font-semibold hover:bg-slate-600 disabled:opacity-40">
              Override
            </button>
          </div>
          {err && <span className="text-sm text-red-400">{err}</span>}
        </div>
      ) : (
        <div className="text-sm text-slate-500">{st.replay ? "Replay: sign-off disabled." : "Waiting for awaiting_approval…"}</div>
      )}
    </div>
  );
}
