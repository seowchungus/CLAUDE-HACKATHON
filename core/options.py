"""Option generator (proposal §5.1): grid eta_shift x gate x FP -> 6-8 Pareto-pruned candidates.

Selection: one favourite per agent (ATC min bank delay, PILOT min misconnects with no hold, GROUND min
overtime), the min-J option, then the rest of the Pareto front on (bank_delay, extra_fuel, misconnects,
overtime), plus 1-2 infeasible-but-tempting options (single failures, H4 gate validity / gate-change notice
and H3 fuel first, lowest J) so the checker has something to catch. Topped up to n_min with infeasible options
when few are feasible. Ids opt_1.. are assigned in (eta_shift, fp, gate) order.
"""
from core.config import load_config
from core.constraints import check_option, failed_ids
from core.metrics import MIN_SHIFT, compute_metrics
from core.types import AgentRole, FPAdj, Option, Scenario

FP_LABEL = {"as_filed": "as filed", "speed_reduction": "speed reduction", "hold_10": "hold 10 min",
            "hold_20": "hold 20 min", "reroute_weather": "weather reroute"}
OBJ = ("bank_delay_added_min", "extra_fuel_min", "misconnected_pax", "ramp_overtime_min")


def make_option(s: Scenario, option_id: str, eta_shift_min: int, gate: str, fp: FPAdj,
                source: str = "generated", proposed_by: AgentRole | None = None,
                parent_option: str | None = None) -> Option:
    return Option(option_id=option_id, eta_shift_min=int(eta_shift_min), gate=gate, fp_adjustment=fp,
                  source=source, proposed_by=proposed_by, parent_option=parent_option,
                  label=f"+{int(eta_shift_min)} min, gate {gate}, {FP_LABEL[fp]}",
                  metrics=compute_metrics(s, eta_shift_min, gate, fp))


def counter_allowed_values(s: Scenario) -> dict[str, list]:
    opt_cfg = load_config()["options"]
    return {"eta_shift_min": list(opt_cfg["eta_shifts_min"]), "gate": [g.gate_id for g in s.gates],
            "fp_adjustment": list(opt_cfg["fp_adjustments"])}


def _dominates(a: Option, b: Option) -> bool:
    va = [getattr(a.metrics, k) for k in OBJ]
    vb = [getattr(b.metrics, k) for k in OBJ]
    return all(x <= y for x, y in zip(va, vb)) and any(x < y for x, y in zip(va, vb))


def generate_options(s: Scenario) -> list[Option]:
    opt_cfg = load_config()["options"]
    n_min, n_max = opt_cfg["n_candidates_min"], opt_cfg["n_candidates_max"]
    fps = list(opt_cfg["fp_adjustments"])
    gates = [g.gate_id for g in s.gates]

    feasible: list[Option] = []
    infeasible: list[tuple[Option, list[str]]] = []
    for shift in opt_cfg["eta_shifts_min"]:
        for fi, fp in enumerate(fps):
            if shift < MIN_SHIFT[fp] or (fp == "speed_reduction" and shift == 0):
                continue  # same eta/fuel as another grid point; skip the duplicate
            rot = (shift // 5 + fi) % len(gates)  # rotate gate preference for diversity
            got_feasible = False
            for gate in gates[rot:] + gates[:rot]:
                o = make_option(s, "tmp", shift, gate, fp)
                fails = failed_ids(check_option(s, o))
                if not fails and not got_feasible:
                    feasible.append(o)
                    got_feasible = True  # one feasible gate per (shift, fp) is enough
                elif fails:
                    infeasible.append((o, fails))

    def J(o: Option) -> float:
        return o.metrics.cost_J

    picks: list[Option] = []

    def add(o: Option | None) -> None:
        if o is not None and len(picks) < n_max and all(
                (p.eta_shift_min, p.gate, p.fp_adjustment) != (o.eta_shift_min, o.gate, o.fp_adjustment)
                and (p.eta_shift_min, p.fp_adjustment) != (o.eta_shift_min, o.fp_adjustment) for p in picks):
            picks.append(o)

    n_bad = 2 if feasible else n_min
    if feasible:
        def best(cands, key):
            cands = list(cands)
            return min(cands, key=key) if cands else None
        add(best(feasible, lambda o: (o.metrics.bank_delay_added_min, o.metrics.throughput_loss, J(o))))  # ATC
        add(best((o for o in feasible if o.metrics.hold_min == 0),
                 lambda o: (o.metrics.misconnected_pax, o.metrics.extra_fuel_min, J(o))))  # PILOT
        add(best(feasible, lambda o: (o.metrics.ramp_overtime_min, o.metrics.gate_change,
                                      -o.metrics.turnaround_buffer_min, J(o))))  # GROUND
        add(best(feasible, J))  # fallback's likely choice
        front = [o for o in feasible if not any(_dominates(p, o) for p in feasible)]
        seen_fp = {p.fp_adjustment for p in picks}
        for o in sorted(front, key=lambda o: (o.fp_adjustment in seen_fp, J(o))):
            if len(picks) >= n_max - n_bad:
                break
            add(o)
            seen_fp.add(o.fp_adjustment)
        for o in sorted(feasible, key=J):  # top up if the front is small
            if len(picks) >= n_min - 1:
                break
            add(o)

    # infeasible-but-tempting: prefer a gate-validity (H4) and a fuel (H3) single failure, then any other,
    # lowest J first; if the feasible set is thin, top up with infeasible options until n_min
    prio = {"H4_gate_validity": 0, "H3_fuel_reserve": 1}
    singles = sorted((x for x in infeasible if len(x[1]) == 1), key=lambda x: (prio.get(x[1][0], 2), J(x[0])))
    used: set[str] = set()
    for o, fails in singles:
        if n_bad <= 0 or len(picks) >= n_max:
            break
        if fails[0] in used:
            continue
        before = len(picks)
        add(o)
        if len(picks) > before:
            used.add(fails[0])
            n_bad -= 1
    for o, _ in sorted(infeasible, key=lambda x: (len(x[1]), J(x[0]))):
        if len(picks) >= n_min:
            break
        add(o)

    picks.sort(key=lambda o: (o.eta_shift_min, fps.index(o.fp_adjustment), o.gate))
    return [o.model_copy(update={"option_id": f"opt_{i + 1}"}) for i, o in enumerate(picks)]
