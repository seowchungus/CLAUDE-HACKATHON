"""Per-option metrics (proposal §5.1). Pure code, never an LLM.

Simplified rules, ILLUSTRATIVE, NOT CERTIFIED:
- eta_new = base_eta + max(eta_shift, min_shift(fp)); a hold of N min (or the +8 min weather reroute)
  delays arrival by at least that much.
- Runway: slots are spaced 3600/aar_reduced s. runway_slot = first time >= eta_new that is >= spacing after
  the preceding bank arrival. Bank followers closer than spacing are pushed back in a cascade; the pushed
  minutes are bank_delay_added_min. separation_margin_s = gap to leader - wake_separation_s[leader-follower]
  (capacity spacing does not guarantee wake spacing, so H1 can still fail).
- arrivals_this_hour = bank arrivals in [slot-30, slot+30) + 1; throughput_loss = max(0, that - aar_reduced).
- Fuel (minutes of flight): speed_reduction absorbs up to 15 min of delay at 0.3 fuel-min/min; hold_N burns
  1.0/min for N min (hold_min = N); reroute_weather absorbs 8 min for a flat +6 fuel-min with the lowest
  turbulence; any remaining delay is flown at normal burn (1.0/min).
  fuel_at_landing = fuel_at_fix - PLANNED_BURN_FIX_TO_LAND - extra_fuel.
- misconnected_pax = sum of pax on connections with sched_dep - (eta_new + taxi_in) < MCT (45 min).
- Gate: needed over [in_block, max(next_departure, in_block + min_turnaround)) capped at +GATE_HOLD_CAP,
  min_turnaround from the destination's workbook row [WB];
  gate_free_from/to is the free gap of that gate around in_block. taxi_path_ok = no blocked taxiway on path.
- turnaround_buffer = next_departure - (eta_new + taxi_in + min_turnaround).
- ramp_overtime = max(0, eta_new + taxi_in + 30 - ramp_shift_end) (cost only; [WB] 8 h shift).
- gate_change = gate != planned_gate; gate_change_notice_min = eta_new - decision_time (H4 needs >= 20 [WB]).
- fuel_at_landing_kg = fuel_at_landing_min x holding burn [WB] (widebody if wake H, else narrowbody).
- cost_J = proposal §5.3 with config.fallback_weights; ramp overtime x ground_overtime_cost_multiplier [WB].
"""
from core.config import load_config
from core.types import FPAdj, Gate, Metrics, Scenario

PLANNED_BURN_FIX_TO_LAND = 12.0
MCT_MIN = 45
RAMP_WORK_AFTER_IN_BLOCK = 30
GATE_HOLD_CAP = 120
GATE_HORIZON = 240
DEFAULT_TAXI_IN = 8

SPEED_ABSORB_MAX, SPEED_BURN = 15, 0.3
HOLD_BURN, NORMAL_BURN = 1.0, 1.0
REROUTE_ABSORB, REROUTE_FUEL = 8, 6.0
MIN_SHIFT = {"as_filed": 0, "speed_reduction": 0, "hold_10": 10, "hold_20": 20, "reroute_weather": REROUTE_ABSORB}
SIZE_RANK = {"S": 0, "M": 1, "L": 2}


def taxi_in(s: Scenario) -> int:
    return int(s.row.taxi_in or DEFAULT_TAXI_IN)


def effective_shift(eta_shift_min: int, fp: str) -> int:
    return max(int(eta_shift_min), MIN_SHIFT[fp])


def hold_minutes(fp: str) -> int:
    return {"hold_10": 10, "hold_20": 20}.get(fp, 0)


def extra_fuel(eta_shift_min: int, fp: str) -> float:
    remaining = effective_shift(eta_shift_min, fp)
    fuel = 0.0
    if fp == "speed_reduction":
        a = min(remaining, SPEED_ABSORB_MAX)
        fuel += SPEED_BURN * a
        remaining -= a
    elif fp in ("hold_10", "hold_20"):
        h = hold_minutes(fp)
        fuel += HOLD_BURN * h
        remaining -= h
    elif fp == "reroute_weather":
        fuel += REROUTE_FUEL
        remaining -= REROUTE_ABSORB
    fuel += NORMAL_BURN * max(0, remaining)
    return round(fuel, 1)


def min_turnaround(s: Scenario) -> int:
    """[WB] per-airport minimum turnaround; legacy config default only for pre-v1.2 scenarios."""
    return int(s.airport_limits.get("min_turnaround_min") or load_config()["thresholds"].get("min_turnaround_min", 35))


def gate_need_window(s: Scenario, eta_new: int) -> tuple[int, int]:
    start = eta_new + taxi_in(s)
    nd = s.next_departure_min if s.next_departure_min is not None else start + 60
    end = min(max(nd, start + min_turnaround(s)), start + GATE_HOLD_CAP)
    return start, end


def _merged(occupied: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for st, en in sorted(occupied):
        if en <= st:
            continue
        if out and st <= out[-1][1]:
            out[-1][1] = max(out[-1][1], en)
        else:
            out.append([st, en])
    return [(a, b) for a, b in out]


def gate_free_window(g: Gate, need_from: int) -> tuple[int, int]:
    """The free gap of gate g containing need_from, or the next free gap if the gate is busy then."""
    busy = _merged(g.occupied)
    free_from = need_from - GATE_HORIZON
    for st, en in busy:
        if en <= need_from:
            free_from = en
        elif st <= need_from < en:
            free_from = en
    nxt = [st for st, _ in busy if st > need_from and st >= free_from]
    free_to = nxt[0] if nxt else max(free_from, need_from) + GATE_HORIZON
    return free_from, free_to


def gate_ok(s: Scenario, g: Gate, eta_new: int) -> bool:
    need_from, need_to = gate_need_window(s, eta_new)
    ff, ft = gate_free_window(g, need_from)
    return (not g.out_of_service and SIZE_RANK[g.size] >= SIZE_RANK[s.aircraft_size]
            and ff <= need_from and ft >= need_to)


def _bank_sequence(s: Scenario, spacing: float) -> list[tuple[float, str]]:
    """FCFS landing times (s) of the bank alone at the reduced AAR, with wake category."""
    seq: list[tuple[float, str]] = []
    prev = None
    for est, wake in sorted((b.est_arr_min * 60.0, b.wake) for b in s.bank if b.est_arr_min is not None):
        t = est if prev is None else max(est, prev + spacing)
        seq.append((t, wake))
        prev = t
    return seq


def _runway(s: Scenario, eta_new: int) -> tuple[int, int, int]:
    """Priority insertion of the disrupted flight at eta_new. Returns (slot_min, separation_margin_s,
    bank_delay_added_min), where bank_delay_added is the extra delay vs. the bank sequenced without us."""
    th = load_config()["thresholds"]
    spacing = 3600.0 / max(1, s.aar_reduced)
    seq = _bank_sequence(s, spacing)
    t = eta_new * 60.0
    leaders = [x for x in seq if x[0] <= t]
    leader = leaders[-1] if leaders else None
    if leader is not None and t - leader[0] < spacing:
        t = leader[0] + spacing
    t = 60.0 * -(-t // 60)  # snap up to the whole minute
    if leader is None:
        margin = 9999
    else:
        margin = int(t - leader[0] - th["wake_separation_s"][f"{leader[1]}-{s.disrupted.wake}"])
    pushed, prev = 0.0, t
    for lt, _ in seq[len(leaders):]:
        new_t = max(lt, prev + spacing)
        pushed += new_t - lt
        prev = new_t
    return int(t // 60), min(margin, 9999), int(round(pushed / 60.0))


def cost_j(m: dict, weights: dict | None = None) -> float:
    cfg = load_config()
    w = weights or cfg["fallback_weights"]
    ot_mult = float(cfg["thresholds"].get("ground_overtime_cost_multiplier", 1.0))
    return round(w["w_d_bank_delay_added"] * m["bank_delay_added_min"]
                 + w["w_f_extra_fuel"] * m["extra_fuel_min"]
                 + w["w_c_misconnected_pax"] * m["misconnected_pax"]
                 + w["w_o_ramp_overtime"] * ot_mult * m["ramp_overtime_min"]
                 + w["w_t_turbulence"] * m["turbulence_idx"]
                 + w["w_q_throughput_loss"] * m["throughput_loss"], 2)


def compute_metrics(s: Scenario, eta_shift_min: int, gate: str, fp: FPAdj) -> Metrics:
    th = load_config()["thresholds"]
    gates = {g.gate_id: g for g in s.gates}
    if gate not in gates:
        raise ValueError(f"unknown gate {gate}")
    g = gates[gate]
    eta_new = s.base_eta_min + effective_shift(eta_shift_min, fp)
    ti = taxi_in(s)
    in_block = eta_new + ti
    slot, margin, bank_delay = _runway(s, eta_new)
    arrivals = 1 + sum(1 for b in s.bank if b.est_arr_min is not None and slot - 30 <= b.est_arr_min < slot + 30)
    xf = extra_fuel(eta_shift_min, fp)
    misconnected = sum((c.pax_connecting or 0) for c in s.connections if c.sched_dep_min - in_block < MCT_MIN)
    need_from, _ = gate_need_window(s, eta_new)
    ff, ft = gate_free_window(g, need_from)
    blocked = set(s.blocked_taxiways)
    turn = min_turnaround(s)
    nd = s.next_departure_min if s.next_departure_min is not None else in_block + 60 + turn
    m = {
        "eta_new_min": eta_new,
        "runway_slot_min": slot,
        "separation_margin_s": margin,
        "fuel_at_landing_min": round(s.fuel_at_fix_min - PLANNED_BURN_FIX_TO_LAND - xf, 1),
        "extra_fuel_min": xf,
        "hold_min": hold_minutes(fp),
        "turbulence_idx": round(float(s.turbulence_by_fp.get(fp, 0.0)), 2),
        "misconnected_pax": int(misconnected),
        "gate": gate,
        "gate_free_from_min": int(ff),
        "gate_free_to_min": int(ft),
        "taxi_path_ok": not any(t in blocked for t in g.taxi_path),
        "turnaround_buffer_min": int(nd - (in_block + turn)),
        "ramp_overtime_min": int(max(0, in_block + RAMP_WORK_AFTER_IN_BLOCK - s.ramp_shift_end_min)),
        "bank_delay_added_min": bank_delay,
        "arrivals_this_hour": arrivals,
        "throughput_loss": max(0, arrivals - s.aar_reduced),
    }
    m["cost_J"] = cost_j(m)
    m["gate_change"] = s.planned_gate is not None and gate != s.planned_gate
    m["gate_change_notice_min"] = (eta_new - s.decision_time_min
                                   if m["gate_change"] and s.decision_time_min is not None else None)
    burn = th["fuel_burn_kg_per_h"]["widebody" if s.disrupted.wake == "H" else "narrowbody"]
    m["fuel_at_landing_kg"] = round(m["fuel_at_landing_min"] * burn / 60.0, 0)
    return Metrics(**m)
