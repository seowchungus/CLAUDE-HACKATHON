import type { Option, Scenario } from "../types";
import { hhmm } from "../types";
import { fuelText, GateChangeBadge } from "./DecisionPanel";

const LABEL_W = 52;
const W = 520;
const RUNWAY_H = 74;
const LANE_H = 17;

/** Runway lane (bank arrivals + the disrupted flight's slot) and gate lanes (occupied + plan window). */
export function Gantt({ s, opt, isPlan }: { s: Scenario; opt: Option | null; isPlan: boolean }) {
  const bankT = s.bank.map((f) => f.est_arr_min ?? f.sched_arr_min);
  const slot = opt?.metrics.runway_slot_min ?? s.base_eta_min;
  const t0 = Math.floor((Math.min(...bankT, slot) - 20) / 30) * 30;
  const t1 = Math.ceil((Math.max(...bankT, slot, s.next_departure_min ?? 0) + 30) / 30) * 30;
  const x = (t: number) => LABEL_W + ((Math.max(t0, Math.min(t1, t)) - t0) / (t1 - t0)) * (W - LABEL_W - 8);
  const gates = s.gates;
  const H = RUNWAY_H + 18 + gates.length * LANE_H + 4;

  // plan gate occupancy: on-block until the tail's next departure (or +60 min)
  const onBlock = opt ? opt.metrics.eta_new_min + Math.round(s.row.taxi_in ?? 0) : null;
  const offBlock = onBlock != null ? (s.next_departure_min ?? onBlock + 60) : null;
  const sepConflict = opt ? opt.metrics.separation_margin_s < 0 : false;

  const ticks: number[] = [];
  for (let t = t0; t <= t1; t += 30) ticks.push(t);

  return (
    <div>
    {opt && (
      <div className="flex flex-wrap items-center gap-x-2 px-2 pt-1 text-[11px] text-slate-400">
        <span className="font-mono text-slate-200">{opt.option_id}</span>
        <span>gate {opt.metrics.gate}{s.planned_gate && s.planned_gate !== opt.metrics.gate ? ` (planned ${s.planned_gate})` : ""}</span>
        <GateChangeBadge o={opt} />
        <span>fuel @ land {fuelText(opt)}</span>
      </div>
    )}
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ fontFamily: "ui-monospace, monospace" }}>
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={0} y2={H} stroke="#1e293b" />
          <text x={x(t) + 2} y={H - 2} fontSize={9} fill="#64748b">
            {hhmm(t)}
          </text>
        </g>
      ))}
      {/* runway lane */}
      <text x={4} y={RUNWAY_H / 2 + 4} fontSize={11} fill="#cbd5e1" fontWeight="bold">
        RWY
      </text>
      <rect x={LABEL_W} y={6} width={W - LABEL_W - 8} height={RUNWAY_H - 12} fill="#0f172a" stroke="#334155" />
      {[...s.bank]
        .sort((a, b) => (a.est_arr_min ?? a.sched_arr_min) - (b.est_arr_min ?? b.sched_arr_min))
        .map((f, i) => {
          const t = f.est_arr_min ?? f.sched_arr_min;
          return (
            <g key={f.flight_id}>
              <rect x={x(t) - 1.5} y={8} width={3} height={RUNWAY_H - 16} fill="#38bdf8" opacity={0.8} />
              <text x={x(t) + 3} y={17 + (i % 3) * 12} fontSize={9} fill="#7dd3fc">
                {f.flight_id}
              </text>
            </g>
          );
        })}
      <g filter={sepConflict ? "url(#glow)" : undefined}>
        <rect x={x(slot) - 3} y={8} width={6} height={RUNWAY_H - 16} fill={sepConflict ? "#ef4444" : "#facc15"} />
        <text x={x(slot) + 5} y={RUNWAY_H - 2} fontSize={9} fontWeight="bold" fill={sepConflict ? "#fca5a5" : "#fde047"}>
          {s.disrupted.flight_id} {hhmm(slot)} {opt ? (isPlan ? "PLAN" : "tentative") : "base ETA"}
        </text>
      </g>
      {/* gate lanes */}
      {gates.map((g, i) => {
        const y = RUNWAY_H + 14 + i * LANE_H;
        const mine = opt?.metrics.gate === g.gate_id && onBlock != null && offBlock != null;
        const conflict =
          mine && (g.out_of_service || g.occupied.some(([a, b]) => onBlock! < b && a < offBlock!));
        return (
          <g key={g.gate_id}>
            <text x={4} y={y + 10} fontSize={9} fill={mine ? "#fde047" : "#94a3b8"}>
              {g.gate_id} {g.size}
              {g.out_of_service ? " OOS" : ""}
            </text>
            <rect x={LABEL_W} y={y} width={W - LABEL_W - 8} height={LANE_H - 3} fill={g.out_of_service ? "#450a0a" : "#0b1220"} />
            {g.occupied.map(([a, b], k) => (
              <rect key={k} x={x(a)} y={y + 1} width={Math.max(1, x(b) - x(a))} height={LANE_H - 5} fill="#475569" rx={2} />
            ))}
            {mine && (
              <g filter={conflict ? "url(#glow)" : undefined}>
                <rect
                  x={x(opt!.metrics.gate_free_from_min)}
                  y={y}
                  width={Math.max(1, x(opt!.metrics.gate_free_to_min) - x(opt!.metrics.gate_free_from_min))}
                  height={LANE_H - 3}
                  fill="none"
                  stroke="#22d3ee"
                  strokeDasharray="3 2"
                />
                <rect x={x(onBlock!)} y={y + 1} width={Math.max(2, x(offBlock!) - x(onBlock!))} height={LANE_H - 5} rx={2}
                  fill={conflict ? "#ef4444" : "#facc15"} opacity={0.9} />
              </g>
            )}
          </g>
        );
      })}
    </svg>
    </div>
  );
}
