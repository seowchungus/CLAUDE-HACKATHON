"""Chaos mutators (proposal §2.3). Each returns a NEW scenario with the event appended to chaos_applied;
mutated fields are marked synthetic in provenance."""
from core.types import ChaosEvent, Scenario


def apply_chaos(s: Scenario, ev: ChaosEvent) -> Scenario:
    s = s.model_copy(deep=True)
    p = ev.params or {}
    prov = dict(s.provenance)
    if ev.kind == "RUNWAY_CLOSURE":
        s.aar_reduced = max(1, round(s.aar_reduced * float(p.get("aar_factor", 0.5))))
        prov["aar_reduced"] = "synthetic"
    elif ev.kind == "TAXIWAY_BLOCK":
        tw = str(p.get("taxiway", s.taxiways[0] if s.taxiways else "A"))
        if tw not in s.blocked_taxiways:
            s.blocked_taxiways = s.blocked_taxiways + [tw]
        prov["blocked_taxiways"] = "synthetic"
    elif ev.kind == "GATE_FAILURE":
        gid = p.get("gate_id") or s.gates[0].gate_id
        dur = int(p.get("duration_min", 90))
        gates = []
        for g in s.gates:
            if g.gate_id == gid:
                g = g.model_copy(update={"out_of_service": True,
                                         "occupied": sorted(g.occupied + [(s.base_eta_min, s.base_eta_min + dur)])})
            gates.append(g)
        s.gates = gates
        prov["gates"] = "synthetic"
    elif ev.kind == "WEATHER_CELL":
        add = float(p.get("turbulence_add", 0.3))
        s.turbulence_by_fp = {fp: round(min(1.0, v + (add * 0.3 if fp == "reroute_weather" else add)), 2)
                              for fp, v in s.turbulence_by_fp.items()}
        s.base_eta_min += int(p.get("extra_delay_min", 15))
        prov["turbulence_by_fp"] = "synthetic"
        prov["base_eta_min"] = "synthetic"
    s.chaos_applied = s.chaos_applied + [ev]
    s.provenance = prov
    return s
