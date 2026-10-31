import type { RunState } from "../useRunStream";

export function RoundTracker({ st }: { st: RunState }) {
  const max = st.started?.max_rounds ?? 3;
  const cur = st.round?.round ?? 0;
  const final = st.consensus ? "CONSENSUS" : st.fallback ? (st.fallback.result.status === "ESCALATE" ? "ESCALATE" : "FALLBACK") : null;
  const steps = Array.from({ length: max }, (_, i) => i + 1);
  const headline = final
    ? `${final}${st.consensus ? ` in R${st.consensus.round}` : ""}`
    : cur
      ? `ROUND ${cur} · ${st.round?.phase}`
      : st.runId
        ? "STARTING…"
        : "READY";
  const headCls =
    final === "CONSENSUS" ? "text-emerald-400" : final === "FALLBACK" ? "text-amber-400" : final === "ESCALATE" ? "text-red-400" : "text-slate-100";
  return (
    <div className="flex items-center gap-6 px-4 py-3">
      <div className="flex items-center gap-2 font-mono text-lg">
        {steps.map((r) => {
          const done = st.roundsEnded.includes(r);
          const active = cur === r && !done;
          return (
            <span key={r} className="flex items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 ${active ? "bg-sky-600 text-white" : done ? "bg-slate-700 text-slate-200" : "border border-slate-700 text-slate-500"}`}
              >
                R{r}
              </span>
              <span className="text-slate-600">→</span>
            </span>
          );
        })}
        <span className={`rounded px-2 py-0.5 ${final ? "bg-slate-800 " + headCls : "border border-slate-700 text-slate-500"}`}>
          {final ?? "CONSENSUS/FALLBACK"}
        </span>
      </div>
      <div className={`text-4xl font-black tracking-tight ${headCls}`}>{headline}</div>
      {st.tentative?.option_id && !final && (
        <div className="text-lg text-slate-300">
          tentative <span className="font-mono font-bold text-sky-300">{st.tentative.option_id}</span>
        </div>
      )}
    </div>
  );
}
