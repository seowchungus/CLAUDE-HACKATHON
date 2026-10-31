import { useEffect, useState } from "react";
import { api } from "../api";
import type { LogEntry, VerifyResult } from "../types";
import { shortC } from "../types";

export function ChainBadge({ v }: { v: VerifyResult | null }) {
  if (!v) return null;
  return v.ok ? (
    <span className="rounded bg-emerald-800 px-2 py-0.5 text-xs font-bold text-emerald-100">chain verified ✓ ({v.n_entries})</span>
  ) : (
    <span className="rounded bg-red-700 px-2 py-0.5 text-xs font-bold text-white">✗ broken at {v.broken_at}</span>
  );
}

/** Fetches /log + /verify whenever `refreshKey` changes (e.g. on run end / approval). */
export function useChain(runId: string | null, refreshKey: unknown) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => setVerify(null), [runId]);
  useEffect(() => {
    if (!runId) {
      setEntries([]);
      return;
    }
    api.log(runId).then(setEntries).catch(() => setEntries([]));
    api.verify(runId).then(setVerify).catch(() => {});
  }, [runId, refreshKey, tick]);
  return { entries, verify, refresh: () => setTick((t) => t + 1) };
}

export function LogDrawer({ runId, entries, verify, onClose }: { runId: string; entries: LogEntry[]; verify: VerifyResult | null; onClose: () => void }) {
  return (
    <div className="fixed inset-y-0 right-0 z-[1000] flex w-[640px] flex-col border-l border-slate-700 bg-slate-950 shadow-2xl">
      <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-3">
        <span className="text-lg font-bold">Consensus log</span>
        <ChainBadge v={verify} />
        <a href={api.logUrl(runId)} download={`${runId}.jsonl`} className="ml-auto rounded bg-sky-700 px-3 py-1 text-sm font-semibold hover:bg-sky-600">
          Download .jsonl
        </a>
        <button onClick={onClose} className="rounded px-2 text-xl text-slate-400 hover:text-white">
          ×
        </button>
      </div>
      {verify && <div className="px-4 py-1 font-mono text-[11px] text-slate-500">head {verify.head_hash}</div>}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-900 text-slate-400">
            <tr>
              <th className="px-2 py-1 text-right">seq</th>
              <th className="px-2 text-left">ts</th>
              <th className="px-2 text-left">actor</th>
              <th className="px-2 text-left">event</th>
              <th className="px-2 text-left">constraints</th>
              <th className="px-2 text-left">hash</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => {
              const broken = verify && !verify.ok && verify.broken_at === e.seq;
              return (
                <tr key={e.seq} className={`border-t border-slate-800 ${broken ? "bg-red-950" : ""}`}>
                  <td className="px-2 py-1 text-right font-mono">{e.seq}</td>
                  <td className="px-2 font-mono text-slate-400">{e.ts.slice(11, 23)}</td>
                  <td className="px-2">{e.actor}</td>
                  <td className="px-2 font-semibold">{e.event_type}</td>
                  <td className="px-2 font-mono text-slate-400">{e.constraint_ids.map(shortC).join(" ")}</td>
                  <td className="px-2 font-mono text-slate-500" title={e.hash}>
                    {e.hash.slice(0, 10)}…
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
