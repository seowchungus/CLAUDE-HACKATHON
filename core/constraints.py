"""Hard-constraint checker H1-H7 (proposal §5.2). Overrides any agent agreement.

Thresholds come from config.thresholds; [WB] = from the organisers' workbook (challenge2_operational_constraints.xlsx).
Rules are simplified illustrations, NOT ICAO / certified values.
H4 also fails a gate change announced less than gate_change_notice_min before arrival [WB].
H5 = flight crew duty only [WB 13 h]: duty remaining - effective delay (eta_new - base_eta, which already
includes any hold) - gate_wait_min >= 0. Ramp overtime is a cost (cost_J), not a hard constraint.
"""
from core.config import load_config
from core.metrics import SIZE_RANK, gate_need_window
from core.types import CheckReport, ConstraintResult, Option, Scenario


def _r(opt: Option, cid: str, passed: bool, value, threshold, detail: str) -> ConstraintResult:
    return ConstraintResult(option_id=opt.option_id, constraint_id=cid, passed=bool(passed),
                            value=None if value is None else float(value),
                            threshold=None if threshold is None else float(threshold), detail=detail[:120])


def check_option(s: Scenario, opt: Option) -> CheckReport:
    th = load_config()["thresholds"]
    m = opt.metrics
    res: list[ConstraintResult] = []

    ok = m.separation_margin_s >= 0
    res.append(_r(opt, "H1_wake_separation", ok, m.separation_margin_s, 0,
                  f"margin {m.separation_margin_s:+d} s {'over' if ok else 'below'} wake minimum (workbook)"))

    ok = m.arrivals_this_hour <= s.aar_reduced
    res.append(_r(opt, "H2_runway_capacity", ok, m.arrivals_this_hour, s.aar_reduced,
                  f"{m.arrivals_this_hour} arrivals {'<=' if ok else '>'} reduced AAR {s.aar_reduced}"))

    res_min = th["fuel_final_reserve_min"]
    ok = m.fuel_at_landing_min >= res_min
    res.append(_r(opt, "H3_fuel_reserve", ok, m.fuel_at_landing_min, res_min,
                  f"fuel {m.fuel_at_landing_min:.1f} min {'>=' if ok else '<'} {res_min} min final reserve (workbook)"))

    gates = {g.gate_id: g for g in s.gates}
    g = gates.get(opt.gate)
    need_from, need_to = gate_need_window(s, m.eta_new_min, m.gate_wait_min)
    if g is None:
        ok, why = False, f"gate {opt.gate} does not exist"
    elif g.out_of_service:
        ok, why = False, f"gate {g.gate_id} out of service"
    elif SIZE_RANK[g.size] < SIZE_RANK[s.aircraft_size]:
        ok, why = False, f"gate {g.gate_id} size {g.size} < aircraft size {s.aircraft_size}"
    elif not (m.gate_free_from_min <= need_from and m.gate_free_to_min >= need_to):
        ok, why = False, (f"gate {g.gate_id} busy: free {m.gate_free_from_min}-{m.gate_free_to_min}, "
                          f"needed {need_from}-{need_to}")
    elif m.gate_change and (m.gate_change_notice_min is None
                            or m.gate_change_notice_min < th["gate_change_notice_min"]):
        ok, why = False, (f"gate change {s.planned_gate}->{g.gate_id} notice {m.gate_change_notice_min} min "
                          f"< {th['gate_change_notice_min']} min (workbook)")
    else:
        ok, why = True, (f"gate {g.gate_id} free and size-compatible"
                         + (f" after {m.gate_wait_min} min ramp wait" if m.gate_wait_min else "")
                         + (f"; change notice {m.gate_change_notice_min} min" if m.gate_change else ""))
    res.append(_r(opt, "H4_gate_validity", ok, None, None, why))

    duty_left = s.flight_crew_duty_remaining_min - (m.eta_new_min - s.base_eta_min) - m.gate_wait_min
    ok = duty_left >= 0
    res.append(_r(opt, "H5_crew_duty", ok, duty_left, 0,
                  f"flight crew duty left {duty_left} min {'>=' if ok else '<'} 0 of 13 h max (workbook)"))

    blocked = [t for t in (g.taxi_path if g else []) if t in s.blocked_taxiways]
    ok = m.taxi_path_ok and g is not None
    res.append(_r(opt, "H6_taxiway_reachability", ok, None, None,
                  "taxi path clear" if ok else f"taxi path blocked at taxiway {','.join(blocked) or '?'}"))

    sev = th["turbulence_severe"]
    ok = m.turbulence_idx < sev
    res.append(_r(opt, "H7_severe_turbulence", ok, m.turbulence_idx, sev,
                  f"turbulence {m.turbulence_idx:.2f} {'<' if ok else '>='} {sev}"))

    return CheckReport(option_id=opt.option_id, feasible=all(r.passed for r in res), results=res)


def check_all(s: Scenario, opts: list[Option]) -> dict[str, CheckReport]:
    return {o.option_id: check_option(s, o) for o in opts}


def failed_ids(rep: CheckReport) -> list[str]:
    return [r.constraint_id for r in rep.results if not r.passed]
