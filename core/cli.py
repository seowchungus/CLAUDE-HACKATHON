"""CLI milestone. Usage:
  python -m core.cli <scenario_id>           print scenario, options, H1-H7 grid and fallback plan
  python -m core.cli --dev N                 same for dev row N (data/dev_rows.json)
  python -m core.cli --export <id> <out>     write {bundle, map} JSON
"""
import json
import sys

from core.bundle import build_bundle
from core.scenario import dev_scenario_ids
from core.types import CONSTRAINT_IDS, ScenarioBundle


def hhmm(m: int | None) -> str:
    if m is None:
        return "--:--"
    d, r = divmod(int(m), 1440)
    return f"{r // 60:02d}:{r % 60:02d}" + (f"+{d}" if d else "")


def tag(s, field: str) -> str:
    p = s.provenance.get(field, "real")
    return " [SYNTHETIC]" if p == "synthetic" else (" [real-derived]" if p == "real_derived" else "")


def render(b: ScenarioBundle) -> str:
    s = b.scenario
    r = s.row
    out = [f"=== {s.scenario_id}  ({s.disrupted.flight_id} {r.origin}->{r.destination}, "
           f"{s.disruption_type} {s.disruption_min} min)  seed={s.seed}",
           f"REAL   sched arr {hhmm(s.disrupted.sched_arr_min)}  base ETA {hhmm(s.base_eta_min)}  "
           f"arr delay {r.arrival_delay}  weather {r.weather_delay}  late-ac {r.late_aircraft_delay}  "
           f"bank {len(s.bank)} flights  connections {len(s.connections)}",
           f"AAR nominal {s.aar_nominal}{tag(s, 'aar_nominal')}  reduced {s.aar_reduced}{tag(s, 'aar_reduced')}  "
           f"size {s.aircraft_size}{tag(s, 'aircraft_size')}  wake {s.disrupted.wake}{tag(s, 'disrupted.wake')}",
           f"fuel@fix {s.fuel_at_fix_min}{tag(s, 'fuel_at_fix_min')}  crew duty {s.flight_crew_duty_remaining_min}"
           f"{tag(s, 'flight_crew_duty_remaining_min')}  ramp shift end {hhmm(s.ramp_shift_end_min)}"
           f"{tag(s, 'ramp_shift_end_min')}  next dep {hhmm(s.next_departure_min)}{tag(s, 'next_departure_min')}",
           f"blocked taxiways {s.blocked_taxiways}  chaos {[c.kind for c in s.chaos_applied]}", ""]
    out.append(f"{'option':9} {'label':38} {'ETA':>7} {'slot':>7} {'sep_s':>5} {'fuel':>5} {'mis':>4} "
               f"{'ot':>3} {'bank':>4} {'arr':>3} {'turb':>4} {'J':>7}  " + " ".join(f"H{i + 1}" for i in range(7)))
    for o in b.options + [b.fcfs]:
        m = o.metrics
        grid = " ".join(" ✓" if res.passed else " ✗" for res in b.checks[o.option_id].results)
        out.append(f"{o.option_id:9} {o.label:38} {hhmm(m.eta_new_min):>7} {hhmm(m.runway_slot_min):>7} "
                   f"{m.separation_margin_s:>5} {m.fuel_at_landing_min:>5.1f} {m.misconnected_pax:>4} "
                   f"{m.ramp_overtime_min:>3} {m.bank_delay_added_min:>4} {m.arrivals_this_hour:>3} "
                   f"{m.turbulence_idx:>4.2f} {m.cost_J:>7.1f}  {grid}")
    out.append("")
    for o in b.options + [b.fcfs]:
        bad = [f"{res.constraint_id}: {res.detail}" for res in b.checks[o.option_id].results if not res.passed]
        if bad:
            out.append(f"  ✗ {o.option_id}: " + "; ".join(bad))
    f = b.fallback
    out.append("")
    out.append(f"FALLBACK (B1): {f.status} {f.option_id or ''}  J={f.cost_J}  ({f.reason})")
    out.append(f"  ranking: {', '.join(f'{i}={j:.1f}' for i, j in f.ranking)}")
    out.append(f"FCFS (B0): {b.fcfs.label}  J={b.fcfs.metrics.cost_J}  "
               f"feasible={b.checks['opt_fcfs'].feasible}")
    assert len(CONSTRAINT_IDS) == 7
    return "\n".join(out)


def export(scenario_id: str, out_path: str) -> None:
    b = build_bundle(scenario_id)
    try:
        from core.mapdata import map_payload
        mp = map_payload(b.scenario).model_dump(mode="json")
    except ImportError:
        mp = None
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"bundle": b.model_dump(mode="json"), "map": mp}, f, indent=1, ensure_ascii=False)
    print(f"wrote {out_path}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--export":
        export(argv[1], argv[2])
        return 0
    sid = dev_scenario_ids()[int(argv[1])] if argv[0] == "--dev" else argv[0]
    print(render(build_bundle(sid)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
