import type { Scenario } from "../types";
import { hhmm } from "../types";

export const Tag = ({ kind }: { kind: "REAL" | "SYNTHETIC" | "DERIVED" | "FIXTURE" | "REPLAY" }) => {
  const cls = {
    REAL: "bg-emerald-900/60 text-emerald-300 border-emerald-700",
    SYNTHETIC: "bg-fuchsia-900/50 text-fuchsia-300 border-fuchsia-700",
    DERIVED: "bg-sky-900/50 text-sky-300 border-sky-700",
    FIXTURE: "bg-amber-900/50 text-amber-300 border-amber-700",
    REPLAY: "bg-orange-900/60 text-orange-300 border-orange-700",
  }[kind];
  return <span className={`ml-1 rounded border px-1 py-px text-[10px] font-semibold tracking-wide ${cls}`}>{kind}</span>;
};

export const provTag = (s: Scenario, field: string) => {
  const p = s.provenance[field];
  if (p === "real") return <Tag kind="REAL" />;
  if (p === "real_derived") return <Tag kind="DERIVED" />;
  if (p) return <Tag kind="SYNTHETIC" />;
  return null;
};

export function ScenarioBar({ s, csvRow }: { s: Scenario; csvRow?: number | null }) {
  const d = s.disrupted;
  const synth: [string, string][] = [
    ["aar_reduced", `AAR ${s.aar_reduced}/h (nominal ${s.aar_nominal})`],
    ["fuel_at_fix_min", `fuel at fix ${s.fuel_at_fix_min} min`],
    ["flight_crew_duty_remaining_min", `crew duty left ${s.flight_crew_duty_remaining_min} min`],
    ["ramp_shift_end_min", `ramp shift ends ${hhmm(s.ramp_shift_end_min)}`],
    ["next_departure_min", `next dep ${hhmm(s.next_departure_min)}`],
    ["aircraft_size", `size ${s.aircraft_size}`],
    ["disrupted.wake", `wake ${d.wake}`],
    ["gates", `${s.gates.length} gates`],
  ];
  const date = `${s.row.year}-${String(s.row.month).padStart(2, "0")}-${String(s.row.day).padStart(2, "0")}`;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-slate-800 bg-slate-900 px-4 py-3">
      <div className="text-2xl font-bold tracking-tight">
        {d.airline} {d.flight_number}{" "}
        <span className="text-slate-300">
          {s.origin.iata}→{s.destination.iata}
        </span>
        <Tag kind="REAL" />
        {s.fixture && <Tag kind="FIXTURE" />}
      </div>
      <div className="text-slate-300">
        {date}
        {csvRow != null && (
          <span className="ml-2 font-mono text-xs text-slate-400" title="0-based data row of data/raw/flights.csv">
            flights.csv row {csvRow.toLocaleString()}
            <Tag kind="REAL" />
          </span>
        )}
      </div>
      <div className="text-lg">
        <span className="font-mono font-semibold text-amber-300">
          {s.disruption_type === "WEATHER" ? "WEATHER_DELAY" : "LATE_AIRCRAFT_DELAY"} {s.disruption_min} min
        </span>
        <Tag kind="REAL" />
      </div>
      <div className="text-slate-300">
        sched arr {hhmm(d.sched_arr_min)} · delayed ETA <span className="font-semibold">{hhmm(s.base_eta_min)}</span>
        <Tag kind="REAL" />
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400">
        {synth.map(([k, label]) => (
          <span key={k}>
            {label}
            {provTag(s, k)}
          </span>
        ))}
      </div>
    </div>
  );
}
