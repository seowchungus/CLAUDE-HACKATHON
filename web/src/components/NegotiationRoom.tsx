import { useState } from "react";
import type { AgentMessage, AgentRole, Option } from "../types";
import { cName, ROLES, shortC } from "../types";
import type { Card, RunState } from "../useRunStream";

const ACTION_CLS: Record<string, string> = {
  PROPOSE: "bg-sky-700",
  COUNTER: "bg-violet-700",
  ACCEPT: "bg-emerald-700",
  REJECT: "bg-red-700",
};

const optLabel = (o?: Option) => (o ? o.label.split(",").slice(0, 2).join(" ·") : "");

function PositionCard({ m, opts, collapsed }: { m: AgentMessage; opts: Record<string, Option>; collapsed: boolean }) {
  const p = m.position;
  const [toggled, setToggled] = useState<boolean | null>(null); // user override; otherwise earlier rounds collapse
  const open = toggled ?? !collapsed;
  const setOpen = (v: boolean) => setToggled(v);
  const [more, setMore] = useState(false);
  const [cites, setCites] = useState(false);
  const top = p?.ranking[0];
  const action = p ? (
    <span className={`rounded px-2 py-0.5 text-xs font-bold ${ACTION_CLS[p.action]}`}>{p.action}</span>
  ) : (
    <span className="rounded bg-red-800 px-2 py-0.5 text-xs font-bold">{m.status.toUpperCase()} → REJECT</span>
  );
  if (!open)
    return (
      <button onClick={() => setOpen(true)} title="click to expand"
        className="flex w-full items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-left text-xs text-slate-400 hover:border-slate-600">
        <span>R{m.round}</span>·<span className="font-semibold">{p?.action ?? m.status}</span>
        {top && <span>· <span className="text-amber-300">★</span> <span className="font-mono text-slate-300">{top}</span></span>}
        <span className="ml-auto">▸</span>
      </button>
    );
  const order = p ? [...p.ranking, ...p.acceptable.filter((x) => !p.ranking.includes(x))] : [];
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm">
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-xs font-semibold text-slate-400">R{m.round}</span>
        {action}
        {top && (
          <span className="text-slate-200">
            <span className="text-amber-300">★</span> <span className="font-mono font-bold text-sky-300">{top}</span>
            <span className="ml-1 text-xs text-slate-400">{optLabel(opts[top])}</span>
          </span>
        )}
        {m.ungrounded && <span className="ml-auto rounded bg-amber-600 px-1.5 py-0.5 text-[10px] font-bold text-black" title="cites a number the table doesn't contain">UNGROUNDED</span>}
        {(collapsed || toggled) && (
          <button onClick={() => setOpen(false)} className={`${m.ungrounded ? "" : "ml-auto"} text-xs text-slate-500 hover:text-slate-300`}>▾</button>
        )}
      </div>
      {p && (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-1" title="ranking, best first; green outline = acceptable, grey struck = not acceptable">
            {order.map((id, i) => {
              const ok = p.acceptable.includes(id);
              return (
                <span key={id}
                  className={`rounded border px-1.5 font-mono text-xs ${ok ? "border-emerald-500 text-emerald-300" : "border-slate-700 text-slate-500 line-through"} ${i === 0 ? "font-bold" : ""}`}>
                  {id}
                </span>
              );
            })}
          </div>
          {p.counter && (
            <div className="mb-2 text-xs">
              <span className="text-slate-400">counter </span>
              <span className="rounded border border-violet-600 px-1.5 font-mono text-violet-300">
                {p.counter.base_option}.{p.counter.param} = {String(p.counter.value)}
              </span>
            </div>
          )}
          {p.red_lines.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1">
              <span className="text-[11px] text-slate-500">red lines</span>
              {p.red_lines.map((r) => (
                <span key={r} className="rounded bg-red-900/70 px-1.5 text-[11px] font-semibold text-red-200" title={r}>
                  {cName(r)}
                </span>
              ))}
            </div>
          )}
          <p className={`text-[15px] leading-snug text-slate-100 ${more ? "" : "line-clamp-3"}`}>{p.rationale}</p>
          {p.rationale.length > 150 && (
            <button onClick={() => setMore(!more)} className="text-xs text-sky-400 hover:underline">{more ? "less" : "more"}</button>
          )}
          {p.cites.length > 0 && (
            <div className="mt-1">
              <button onClick={() => setCites(!cites)} className="text-[11px] text-slate-500 hover:text-slate-300">
                {p.cites.length} cites {cites ? "▾" : "▸"}
              </button>
              {cites && <div className="font-mono text-[11px] text-slate-500">{p.cites.join(", ")}</div>}
            </div>
          )}
        </>
      )}
      {m.errors.length > 0 && <div className="mt-1 text-xs text-red-400">{m.errors.join("; ")}</div>}
      <div className="mt-2 flex gap-3 text-[11px] text-slate-500">
        <span>{(m.latency_ms / 1000).toFixed(1)} s</span>
        {m.status !== "ok" && <span className="text-red-400">status {m.status}</span>}
        {m.retries > 0 && <span className="text-amber-400">retries {m.retries}</span>}
      </div>
    </div>
  );
}

function CardView({ c, opts, latest }: { c: Card; opts: Record<string, Option>; latest: number }) {
  if (c.kind === "thinking")
    return (
      <div className="animate-pulse rounded-lg border border-dashed border-slate-700 p-3 text-sm text-slate-400">
        R{c.round} thinking…
      </div>
    );
  if (c.kind === "position") return <PositionCard m={c.msg} opts={opts} collapsed={c.round < latest} />;
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
  const opts = Object.fromEntries([...st.options, ...(st.fcfs ? [st.fcfs] : [])].map((o) => [o.option_id, o]));
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
            {(() => {
              const cs = byRole(r);
              const latest = Math.max(0, ...cs.map((c) => c.round)); // earlier rounds collapse to one line
              return cs.map((c) => <CardView key={c.seq} c={c} opts={opts} latest={latest} />);
            })()}
          </div>
        ))}
      </div>
    </div>
  );
}
