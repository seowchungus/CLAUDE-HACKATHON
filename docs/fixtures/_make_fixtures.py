"""Generates the hand-made contract fixtures (MANAGER). Pure stdlib.
Run: python3 docs/fixtures/_make_fixtures.py
These are FIXTURES ("fixture": true), not real DOT rows and not real metric computations.
"""
import hashlib, json, os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SID = "2015-01-02_AA1234_DFW-ORD"
RUN = "run_20261031T034100_a1b2c3"
CIDS = ["H1_wake_separation", "H2_runway_capacity", "H3_fuel_reserve", "H4_gate_validity",
        "H5_crew_duty", "H6_taxiway_reachability", "H7_severe_turbulence"]
WEIGHTS = {"w_d_bank_delay_added": 1.0, "w_f_extra_fuel": 0.8, "w_c_misconnected_pax": 2.0,
           "w_o_ramp_overtime": 0.5, "w_t_turbulence": 20.0, "w_q_throughput_loss": 5.0}

AP = {
    "DFW": ("Dallas/Fort Worth International Airport", "Dallas-Fort Worth", "TX", 32.89595, -97.0372),
    "ORD": ("Chicago O'Hare International Airport", "Chicago", "IL", 41.9796, -87.90446),
    "LGA": ("LaGuardia Airport", "New York", "NY", 40.77724, -73.87261),
    "LAX": ("Los Angeles International Airport", "Los Angeles", "CA", 33.94254, -118.40807),
    "ATL": ("Hartsfield-Jackson Atlanta International Airport", "Atlanta", "GA", 33.64044, -84.42694),
    "DEN": ("Denver International Airport", "Denver", "CO", 39.85841, -104.667),
    "BOS": ("Gen. Edward Lawrence Logan International Airport", "Boston", "MA", 42.36435, -71.00518),
    "MSP": ("Minneapolis-Saint Paul International Airport", "Minneapolis", "MN", 44.88055, -93.21692),
    "SFO": ("San Francisco International Airport", "San Francisco", "CA", 37.619, -122.37484),
    "MIA": ("Miami International Airport", "Miami", "FL", 25.79325, -80.29056),
    "PHX": ("Phoenix Sky Harbor International Airport", "Phoenix", "AZ", 33.43417, -112.00806),
    "SEA": ("Seattle-Tacoma International Airport", "Seattle", "WA", 47.44898, -122.30931),
    "DCA": ("Ronald Reagan Washington National Airport", "Arlington", "VA", 38.85208, -77.03772),
}

def airport(c):
    n, city, st, lat, lon = AP[c]
    return {"iata": c, "name": n, "city": city, "state": st, "lat": lat, "lon": lon}

def fl(fid, o, d, dep, arr, est, role, wake, pax=None, tail=None):
    return {"flight_id": fid, "airline": fid[:2], "flight_number": int(fid[2:]), "tail_number": tail,
            "origin": o, "destination": d, "sched_dep_min": dep, "sched_arr_min": arr,
            "est_arr_min": est, "role": role, "wake": wake, "pax_connecting": pax}

row = {"year": 2015, "month": 1, "day": 2, "airline": "AA", "flight_number": 1234, "tail_number": "N4XAAA",
       "origin": "DFW", "destination": "ORD", "scheduled_departure": 1400, "departure_delay": 52.0,
       "scheduled_arrival": 1630, "arrival_delay": 55.0, "distance": 802, "scheduled_time": 150.0,
       "air_time": 118.0, "taxi_in": 9.0, "taxi_out": 21.0, "weather_delay": 48.0,
       "late_aircraft_delay": 0.0, "air_system_delay": 7.0}

bank = [
    fl("UA1501", "LGA", "ORD", 870, 1015, 1032, "bank", "M"),
    fl("AA2210", "LAX", "ORD", 690, 1030, 1041, "bank", "H"),
    fl("UA0918", "SFO", "ORD", 700, 1035, 1048, "bank", "H"),
    fl("WN3307", "DEN", "ORD", 880, 1040, 1046, "bank", "M"),
    fl("AA1730", "ATL", "ORD", 900, 1045, 1052, "bank", "M"),
    fl("DL2244", "MSP", "ORD", 975, 1050, 1058, "bank", "L"),
    fl("UA0610", "BOS", "ORD", 905, 1055, 1063, "bank", "M"),
    fl("AA0388", "PHX", "ORD", 795, 1060, 1066, "bank", "M"),
    fl("UA1144", "SEA", "ORD", 720, 1070, 1074, "bank", "H"),
    fl("AA2671", "MIA", "ORD", 880, 1075, 1080, "bank", "M"),
]
conns = [
    fl("AA0144", "ORD", "LGA", 1035, 1170, None, "connection", "M", 14),
    fl("AA0901", "ORD", "BOS", 1060, 1195, None, "connection", "M", 9),
    fl("AA2032", "ORD", "MIA", 1085, 1260, None, "connection", "M", 21),
    fl("AA1580", "ORD", "SEA", 1120, 1395, None, "connection", "H", 6),
    fl("AA0475", "ORD", "DCA", 1140, 1250, None, "connection", "M", 11),
]
gates = []
paths = {"A": ["A"], "B": ["A", "B"], "C": ["C", "D"]}
sizes = {"A": "L", "B": "M", "C": "M"}
occ = {"A1": [(1000, 1070)], "A2": [(1040, 1110)], "B2": [(1030, 1090)], "C3": [(1060, 1140)]}
for c in "ABC":
    for i in range(1, 5):
        g = f"{c}{i}"
        gates.append({"gate_id": g, "concourse": c, "size": sizes[c], "taxi_path": paths[c],
                      "occupied": occ.get(g, []), "out_of_service": False})

prov = {k: "real" for k in ["row", "disruption_type", "disruption_min", "origin", "destination",
                            "bank", "connections", "base_eta_min"]}
prov.update({"aar_nominal": "real_derived", "aar_reduced": "synthetic", "aircraft_size": "synthetic",
             "fuel_at_fix_min": "synthetic", "flight_crew_duty_remaining_min": "synthetic",
             "ramp_shift_end_min": "synthetic", "next_departure_min": "synthetic", "gates": "synthetic",
             "taxiways": "synthetic", "turbulence_by_fp": "synthetic", "bank.wake": "synthetic",
             "connections.pax_connecting": "synthetic", "disrupted.wake": "synthetic"})

scenario = {
    "scenario_id": SID, "seed": 1234002, "fixture": True, "row": row,
    "disruption_type": "WEATHER", "disruption_min": 48,
    "origin": airport("DFW"), "destination": airport("ORD"),
    "disrupted": fl("AA1234", "DFW", "ORD", 840, 990, 1045, "disrupted", "M", tail="N4XAAA"),
    "bank": bank, "connections": conns, "base_eta_min": 1045,
    "aar_nominal": 96, "aar_reduced": 67, "aircraft_size": "M", "fuel_at_fix_min": 52.0,
    "flight_crew_duty_remaining_min": 140, "ramp_shift_end_min": 1080, "next_departure_min": 1130,
    "gates": gates, "taxiways": ["A", "B", "C", "D"], "blocked_taxiways": [],
    "turbulence_by_fp": {"as_filed": 0.45, "speed_reduction": 0.4, "hold_10": 0.35, "hold_20": 0.35,
                         "reroute_weather": 0.15},
    "chaos_applied": [], "provenance": prov,
}

FP_LABEL = {"as_filed": "as filed", "speed_reduction": "speed reduction", "hold_10": "hold 10 min",
            "hold_20": "hold 20 min", "reroute_weather": "weather reroute"}

def metrics(shift, gate, fp, fuel, misc, ovt, bank_d, sep, arrivals, turb, gfrom, gto, taxi_ok=True):
    hold = {"hold_10": 10, "hold_20": 20}.get(fp, 0)
    eta = 1045 + shift
    extra = round(52.0 - 22.0 - fuel + 0.0, 1) if fuel < 30 else round(max(0.0, 22.0 - (fuel - 30.0)) * 0.5, 1)
    thr = max(0, arrivals - 67)
    J = (WEIGHTS["w_d_bank_delay_added"] * bank_d + WEIGHTS["w_f_extra_fuel"] * extra +
         WEIGHTS["w_c_misconnected_pax"] * misc + WEIGHTS["w_o_ramp_overtime"] * ovt +
         WEIGHTS["w_t_turbulence"] * turb + WEIGHTS["w_q_throughput_loss"] * thr)
    return {"eta_new_min": eta, "runway_slot_min": eta - 4, "separation_margin_s": sep,
            "fuel_at_landing_min": fuel, "extra_fuel_min": extra, "hold_min": hold, "turbulence_idx": turb,
            "misconnected_pax": misc, "gate": gate, "gate_free_from_min": gfrom, "gate_free_to_min": gto,
            "taxi_path_ok": taxi_ok, "turnaround_buffer_min": 1130 - (eta + 9 + 35),
            "ramp_overtime_min": ovt, "bank_delay_added_min": bank_d, "arrivals_this_hour": arrivals,
            "throughput_loss": thr, "cost_J": round(J, 1)}

def opt(oid, shift, gate, fp, m, source="generated", by=None, parent=None):
    lab = f"+{shift} min, gate {gate}, {FP_LABEL[fp]}"
    return {"option_id": oid, "eta_shift_min": shift, "gate": gate, "fp_adjustment": fp, "source": source,
            "proposed_by": by, "parent_option": parent, "label": lab, "metrics": m}

opts = [
    opt("opt_1", 0, "A3", "as_filed", metrics(0, "A3", "as_filed", 44.0, 0, 0, 9, 15, 66, 0.45, 960, 1200)),
    opt("opt_2", 10, "A4", "speed_reduction", metrics(10, "A4", "speed_reduction", 41.5, 14, 0, 3, 40, 65, 0.4, 960, 1200)),
    opt("opt_3", 15, "B3", "reroute_weather", metrics(15, "B3", "reroute_weather", 36.0, 14, 0, 2, 75, 64, 0.15, 960, 1200)),
    opt("opt_4", 5, "C1", "speed_reduction", metrics(5, "C1", "speed_reduction", 43.0, 0, 0, 5, 30, 66, 0.4, 960, 1200)),
    opt("opt_5", 20, "B1", "hold_20", metrics(20, "B1", "hold_20", 27.5, 23, 0, 0, 120, 63, 0.35, 960, 1200)),
    opt("opt_6", 0, "B2", "as_filed", metrics(0, "B2", "as_filed", 44.0, 0, 0, 9, 15, 66, 0.45, 1090, 1200)),
]
fcfs = opt("opt_fcfs", 0, "A3", "as_filed", metrics(0, "A3", "as_filed", 44.0, 0, 0, 9, 15, 66, 0.45, 960, 1200), source="fcfs")
counter = opt("opt_c1", 5, "A3", "speed_reduction", metrics(5, "A3", "speed_reduction", 43.0, 0, 0, 5, 30, 66, 0.4, 960, 1200),
              source="counter", by="GROUND", parent="opt_4")

def check(o):
    m = o["metrics"]; fails = {}
    if m["fuel_at_landing_min"] < 30:
        fails["H3_fuel_reserve"] = (m["fuel_at_landing_min"], 30, f"fuel {m['fuel_at_landing_min']} min < 30 min final reserve")
    if o["gate"] == "B2":
        fails["H4_gate_validity"] = (None, None, "gate B2 occupied 17:10-18:10 by another aircraft")
    vals = {"H1_wake_separation": (m["separation_margin_s"], 0, f"margin +{m['separation_margin_s']} s over wake minimum"),
            "H2_runway_capacity": (m["arrivals_this_hour"], 67, f"{m['arrivals_this_hour']} arrivals <= reduced AAR 67"),
            "H3_fuel_reserve": (m["fuel_at_landing_min"], 30, f"fuel {m['fuel_at_landing_min']} min >= 30 min final reserve"),
            "H4_gate_validity": (None, None, f"gate {o['gate']} free and size-compatible"),
            "H5_crew_duty": (140 - o["eta_shift_min"], 0, f"crew duty remaining {140 - o['eta_shift_min']} min; ramp overtime 0 <= 60"),
            "H6_taxiway_reachability": (None, None, "taxi path clear"),
            "H7_severe_turbulence": (m["turbulence_idx"], 0.7, f"turbulence {m['turbulence_idx']} < 0.7")}
    res = []
    for c in CIDS:
        v, t, d = fails.get(c, vals[c])
        res.append({"option_id": o["option_id"], "constraint_id": c, "passed": c not in fails,
                    "value": v, "threshold": t, "detail": d})
    return {"option_id": o["option_id"], "feasible": not fails, "results": res}

checks = {o["option_id"]: check(o) for o in opts + [fcfs]}
feas = sorted([(o["option_id"], o["metrics"]["cost_J"]) for o in opts if checks[o["option_id"]]["feasible"]], key=lambda x: x[1])
fallback = {"status": "PLAN", "option_id": feas[0][0], "cost_J": feas[0][1], "ranking": feas, "weights": WEIGHTS,
            "reason": f"min J among {len(feas)} feasible options"}
bundle = {"scenario": scenario, "options": opts, "checks": checks, "fallback": fallback, "fcfs": fcfs}

# ---- map payload
def map_payload():
    flights = [scenario["disrupted"]] + bank + conns
    codes = sorted({f["origin"] for f in flights} | {f["destination"] for f in flights})
    airports = [{"iata": c, "name": AP[c][0], "lat": AP[c][3], "lon": AP[c][4],
                 "role": "destination" if c == "ORD" else "origin" if c == "DFW" else "other"} for c in codes]
    mf = [{"flight_id": f["flight_id"], "role": f["role"], "origin": f["origin"], "destination": f["destination"],
           "origin_lat": AP[f["origin"]][3], "origin_lon": AP[f["origin"]][4],
           "dest_lat": AP[f["destination"]][3], "dest_lon": AP[f["destination"]][4],
           "sched_dep_min": f["sched_dep_min"], "sched_arr_min": f["sched_arr_min"],
           "est_arr_min": f["est_arr_min"], "position_estimated": True} for f in flights]
    return {"focus_airport": "ORD", "airports": airports, "flights": mf, "now_min": 960}

with open(os.path.join(HERE, "scenario_bundle.json"), "w") as f:
    json.dump({"bundle": bundle, "map": map_payload()}, f, indent=1)
with open(os.path.join(HERE, "scenarios_list.json"), "w") as f:
    json.dump([
        {"scenario_id": SID, "date": "2015-01-02", "flight_id": "AA1234", "origin": "DFW", "destination": "ORD",
         "disruption_type": "WEATHER", "disruption_min": 48},
        {"scenario_id": "2015-01-02_UA0918_SFO-ORD", "date": "2015-01-02", "flight_id": "UA918", "origin": "SFO",
         "destination": "ORD", "disruption_type": "LATE_AIRCRAFT", "disruption_min": 34},
    ], f, indent=1)

# ---- run events with a real hash chain
def canon(x): return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
t0 = datetime(2026, 10, 31, 3, 41, 0, tzinfo=timezone.utc)
log, events = [], []
prev = "0" * 64
def entry(etype, actor, payload, cids=(), synth=()):
    global prev
    seq = len(log)
    e = {"seq": seq, "ts": (t0 + timedelta(milliseconds=700 * seq)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
         "run_id": RUN, "scenario_id": SID,
         "source_row": {"date": "2015-01-02", "airline": "AA", "flight_number": 1234},
         "event_type": etype, "actor": actor, "constraint_ids": list(cids), "synthetic_fields": list(synth),
         "payload": payload, "prev_hash": prev}
    e["hash"] = hashlib.sha256((prev + canon(e)).encode()).hexdigest()
    prev = e["hash"]; log.append(e); return e
def emit(etype, actor, data, cids=()):
    e = entry(etype, actor, data, cids)
    events.append({"type": etype, "run_id": RUN, "seq": len(events), "ts": e["ts"], "log_hash": e["hash"], "data": data})

entry("scenario_loaded", "SYSTEM", {"scenario": scenario}, synth=[k for k, v in prov.items() if v == "synthetic"])
MODELS = {"ATC": "gemini-3.8-flash", "PILOT": "gemini-3.8-flash", "GROUND": "gemini-3.8-flash", "NARRATOR": "gemini-flash-lite-latest"}
emit("run_started", "COORDINATOR", {"scenario_id": SID, "max_rounds": 3, "llm_enabled": True, "models": MODELS,
                                    "parent_run_id": None, "chaos_applied": []})
emit("options", "CHECKER", {"options": opts, "checks": checks, "fallback": fallback, "fcfs": fcfs}, CIDS)

def pos(agent, rnd, action, ranking, acceptable, rationale, cites, counter=None, red=()):
    return {"agent": agent, "round": rnd, "status": "ok", "model": "gemini-3.8-flash", "latency_ms": 2100 + 150 * len(agent),
            "tokens_in": 3900, "tokens_out": 210, "retries": 0, "ungrounded": False, "errors": [],
            "position": {"agent": agent, "round": rnd, "action": action, "ranking": ranking, "acceptable": acceptable,
                         "counter": counter, "red_lines": list(red), "cites": cites, "rationale": rationale}}

# R1
emit("round_started", "COORDINATOR", {"round": 1, "phase": "PROPOSE", "candidates": [o["option_id"] for o in opts], "tentative": None})
for a in ("ATC", "PILOT", "GROUND"):
    emit("agent_thinking", "COORDINATOR", {"round": 1, "agent": a})
emit("agent_position", "ATC", pos("ATC", 1, "PROPOSE", ["opt_3", "opt_4", "opt_2", "opt_1"], ["opt_2", "opt_3", "opt_4", "opt_1"],
     "opt_3 gives the widest wake margin (opt_3.separation_margin_s) and keeps arrivals under the reduced AAR (opt_3.arrivals_this_hour).",
     ["opt_3.separation_margin_s", "opt_3.arrivals_this_hour"], red=["H1_wake_separation", "H2_runway_capacity"]))
emit("agent_position", "PILOT", pos("PILOT", 1, "COUNTER", ["opt_4", "opt_1", "opt_3"], ["opt_1", "opt_3", "opt_4"],
     "opt_4 keeps misconnects at opt_4.misconnected_pax with fuel opt_4.fuel_at_landing_min; prefer speed reduction over holding. Countering gate to B2 for a shorter walk to connections.",
     ["opt_4.misconnected_pax", "opt_4.fuel_at_landing_min"], counter={"base_option": "opt_4", "param": "gate", "value": "B2"},
     red=["H3_fuel_reserve", "H7_severe_turbulence"]))
emit("agent_position", "GROUND", pos("GROUND", 1, "COUNTER", ["opt_5", "opt_4", "opt_1"], ["opt_1", "opt_4", "opt_5"],
     "opt_5 lands with zero overtime (opt_5.ramp_overtime_min). Countering opt_4 to gate A3, which is free and large enough.",
     ["opt_5.ramp_overtime_min", "opt_4.turnaround_buffer_min"], counter={"base_option": "opt_4", "param": "gate", "value": "A3"},
     red=["H4_gate_validity", "H5_crew_duty"]))
bad = opt("opt_4", 5, "B2", "speed_reduction", opts[3]["metrics"]); bad_check = check(bad)
emit("counter_checked", "CHECKER", {"round": 1, "agent": "PILOT", "counter": {"base_option": "opt_4", "param": "gate", "value": "B2"},
     "accepted": False, "option_id": None, "reason": "H4_gate_validity: gate B2 occupied 17:10-18:10 by another aircraft", "check": bad_check},
     ["H4_gate_validity"])
emit("counter_checked", "CHECKER", {"round": 1, "agent": "GROUND", "counter": {"base_option": "opt_4", "param": "gate", "value": "A3"},
     "accepted": True, "option_id": "opt_c1", "reason": "all hard constraints pass", "check": None}, CIDS)
opts2 = opts + [counter]; checks["opt_c1"] = check(counter)
emit("options", "CHECKER", {"options": opts2, "checks": checks, "fallback": fallback, "fcfs": fcfs}, CIDS)
emit("veto", "CHECKER", {"round": 1, "option_id": "opt_5", "agents": ["GROUND"], "failed": ["H3_fuel_reserve"],
     "reason": "GROUND ranked opt_5 first but fuel 27.5 min < 30 min final reserve; checker overrides"}, ["H3_fuel_reserve"])
emit("tentative", "COORDINATOR", {"round": 1, "option_id": "opt_c1", "agreement_set": ["opt_1", "opt_4", "opt_c1"],
     "minmax_rank": {"opt_c1": 2, "opt_4": 2, "opt_1": 4}})
emit("round_ended", "COORDINATOR", {"round": 1, "all_accept": False, "actions": {"ATC": "PROPOSE", "PILOT": "COUNTER", "GROUND": "COUNTER"}})
# R2
emit("round_started", "COORDINATOR", {"round": 2, "phase": "RESPOND", "candidates": [o["option_id"] for o in opts2], "tentative": "opt_c1"})
for a in ("ATC", "PILOT", "GROUND"):
    emit("agent_thinking", "COORDINATOR", {"round": 2, "agent": a})
acc = {"ATC": "opt_c1 keeps a wake margin of opt_c1.separation_margin_s and arrivals within AAR (opt_c1.arrivals_this_hour). Acceptable.",
       "PILOT": "opt_c1 has zero misconnects (opt_c1.misconnected_pax) and fuel opt_c1.fuel_at_landing_min with no holding. Accept.",
       "GROUND": "opt_c1 uses free gate A3 with no ramp overtime (opt_c1.ramp_overtime_min). Accept."}
cites = {"ATC": ["opt_c1.separation_margin_s", "opt_c1.arrivals_this_hour"],
         "PILOT": ["opt_c1.misconnected_pax", "opt_c1.fuel_at_landing_min"], "GROUND": ["opt_c1.ramp_overtime_min"]}
for a in ("ATC", "PILOT", "GROUND"):
    emit("agent_position", a, pos(a, 2, "ACCEPT", ["opt_c1"], ["opt_c1", "opt_4"], acc[a], cites[a]))
emit("tentative", "COORDINATOR", {"round": 2, "option_id": "opt_c1", "agreement_set": ["opt_c1", "opt_4"], "minmax_rank": {"opt_c1": 1, "opt_4": 2}})
emit("round_ended", "COORDINATOR", {"round": 2, "all_accept": True, "actions": {"ATC": "ACCEPT", "PILOT": "ACCEPT", "GROUND": "ACCEPT"}})
emit("consensus", "COORDINATOR", {"round": 2, "option_id": "opt_c1", "plan": counter, "check": checks["opt_c1"], "accepts": acc}, CIDS)
emit("narration", "NARRATOR", {"text": "AA1234 DFW-ORD, delayed 48 min by weather. All three agents agreed in round 2 on landing 5 min later than the delayed ETA with a speed reduction, at gate A3. No passengers misconnect and no ramp overtime is needed. A pilot request for gate B2 was blocked because B2 is occupied. A ground preference for a 20-min hold was vetoed: it would land below the 30-min fuel reserve."})
emit("awaiting_approval", "COORDINATOR", {"decision_source": "CONSENSUS", "option_id": "opt_c1", "rounds_used": 2})
emit("run_ended", "COORDINATOR", {"final_state": "CONSENSUS", "rounds_used": 2, "latency_ms": 9800, "chain_ok": True, "n_llm_calls": 6})

with open(os.path.join(HERE, "run_events.jsonl"), "w") as f:
    for e in events: f.write(json.dumps(e) + "\n")
with open(os.path.join(HERE, "run_log.jsonl"), "w") as f:
    for e in log: f.write(json.dumps(e) + "\n")
print(f"wrote fixtures: {len(opts)} options, {len(events)} events, {len(log)} log entries, fallback={fallback['option_id']}")
