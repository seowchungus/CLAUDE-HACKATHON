import type { AgentMessage, AgentRole } from "../types";
import { ROLES, shortC } from "../types";
import type { Card, RunState } from "../useRunStream";

const ACTION_CLS: Record<string, string> = {
  PROPOSE: "bg-sky-700",
  COUNTER: "bg-violet-700",
  ACCEPT: "bg-emerald-700",
  REJECT: "bg-red-700",
};

function PositionCard({ m }: { m: AgentMessage }) {
  const p = m.position;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-slate-400">R{m.round}</span>
        {p ? (
          <span className={`rounded px-2 py-0.5 text-xs font-bold ${ACTION_CLS[p.action]}`}>{p.action}</span>
        ) : (
          <span className="rounded bg-red-800 px-2 py-0.5 text-xs font-bold">{m.status.toUpperCase()} → REJECT</span>
        )}
      </div>
      {p && (
        <>
          <div className="mb-1">
            <span className="text-slate-400">ranking </span>
            {p.ranking.map((id, i) => (
              <span key={id} className={`mr-1 font-mono ${i === 0 ? "font-bold text-sky-300" : "text-slate-300"}`}>
                {id}
              </span>
            ))}
          </div>
          <div className="mb-1">
            <span className="text-slate-400">acceptable </span>
            <span className="font-mono text-emerald-300">{p.acceptable.join(" ") || "—"}</span>
          </div>
          {p.counter && (
            <div className="mb-1">
              <span className="text-slate-400">counter </span>
              <span className="font-mono text-violet-300">
                {p.counter.base_option}.{p.counter.param} = {String(p.counter.value)}
              </span>
            </div>
          )}
          {p.red_lines.length > 0 && (
            <div className="mb-1">
              <span className="text-slate-400">red lines </span>
              {p.red_lines.map((r) => (
                <span key={r} className="mr-1 rounded bg-red-950 px-1 font-mono text-xs text-red-300" title={r}>
                  {shortC(r)}
                </span>
              ))}
            </div>
          )}
          <p className="my-2 leading-snug text-slate-200">{p.rationale}</p>
          {p.cites.length > 0 && <div className="font-mono text-[11px] text-slate-500">cites: {p.cites.join(", ")}</div>}
        </>
      )}
      {m.errors.length > 0 && <div className="mt-1 text-xs text-red-400">{m.errors.join("; ")}</div>}
      <div className="mt-2 flex gap-3 text-[11px] text-slate-500">
        <span>{m.model}</span>
        <span>{m.latency_ms} ms</span>
        <span>status {m.status}</span>
        {m.retries > 0 && <span className="text-amber-400">retries {m.retries}</span>}
        {m.ungrounded && <span className="text-amber-400">UNGROUNDED</span>}
      </div>
    </div>
  );
}

function CardView({ c }: { c: Card }) {
  if (c.kind === "thinking")
    return (
      <div className="animate-pulse rounded-lg border border-dashed border-slate-700 p-3 text-sm text-slate-400">
        R{c.round} thinking…
      </div>
    );
  if (c.kind === "position") return <PositionCard m={c.msg} />;
  const cc = c.cc;
  return cc.accepted ? (
    <div className="rounded-lg border border-emerald-700 bg-emerald-950/50 p-3 text-sm">
      <div className="font-bold text-emerald-300">
        ✓ counter accepted → <span className="font-mono">{cc.option_id}</span>
      </div>
      <div className="font-mono text-xs text-slate-300">
        {cc.counter.base_option}.{cc.counter.param} = {String(cc.counter.value)}
      </div>
      <div className="text-xs text-slate-400">{cc.reason}</div>
    </div>
  ) : (
    <div className="shake rounded-lg border-2 border-red-600 bg-red-950/70 p-3 text-sm">
      <div className="font-bold text-red-300">✗ COUNTER REJECTED BY CHECKER</div>
      <div className="font-mono text-xs text-slate-300">
        {cc.counter.base_option}.{cc.counter.param} = {String(cc.counter.value)}
      </div>
      <div className="mt-1 text-red-200">{cc.reason}</div>
    </div>
  );
}

export function NegotiationRoom({ st }: { st: RunState }) {
  const byRole = (r: AgentRole) => st.cards.filter((c) => c.agent === r).sort((a, b) => b.seq - a.seq);
  return (
    <div className="flex flex-col gap-2">
      {st.vetoes.map((v, i) => (
        <div key={i} className="rounded-lg border-2 border-red-500 bg-red-900/60 px-4 py-2 text-lg font-semibold text-red-100">
          ⛔ VETO R{v.round}: <span className="font-mono">{v.option_id}</span> fails {v.failed.map(shortC).join(", ")} ({v.agents.join(", ")}).{" "}
          <span className="text-base font-normal">{v.reason}</span>
        </div>
      ))}
      {st.fallback && st.fallback.reason !== "NO_CONSENSUS" && (
        <div className="rounded-lg border-2 border-amber-500 bg-amber-900/50 px-4 py-2 text-lg font-semibold text-amber-100">
          LLM path unavailable ({st.fallback.reason}): deterministic fallback in control
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        {ROLES.map((r) => (
          <div key={r} className="flex min-h-40 flex-col gap-2">
            <div className="flex items-baseline justify-between border-b border-slate-700 pb-1">
              <span className="text-xl font-bold">{r}</span>
              <span className="text-xs text-slate-500">{st.started?.models[r]}</span>
            </div>
            {byRole(r).map((c) => (
              <CardView key={c.seq} c={c} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
