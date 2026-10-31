"""Deterministic fallback (proposal §5.3) and FCFS baseline (§8.2). No LLM, no import from agents/.

B0 fcfs: eta_shift 0 (runway slot snapped by metrics), the planned gate if free, else the first free compatible
reachable gate (naive: ignores the gate-change notice rule), as filed.
B1 solve: filter hard-feasible -> min cost_J -> tie-break lowest eta_shift then option_id.
No feasible option -> ESCALATE (no safe automated plan; diversion candidate).
"""
from core.config import load_config
from core.metrics import cost_j, gate_ok
from core.options import make_option
from core.types import CheckReport, FallbackResult, Option, Scenario


def fcfs(s: Scenario) -> Option:
    blocked = set(s.blocked_taxiways)
    eta = s.base_eta_min
    usable = [g.gate_id for g in s.gates if gate_ok(s, g, eta) and not (set(g.taxi_path) & blocked)]
    gate = s.planned_gate if s.planned_gate in usable else (usable[0] if usable else s.planned_gate or s.gates[0].gate_id)
    return make_option(s, "opt_fcfs", 0, gate, "as_filed", source="fcfs")


def solve(s: Scenario, opts: list[Option], checks: dict[str, CheckReport],
          weights: dict | None = None) -> FallbackResult:
    w = dict(weights or load_config()["fallback_weights"])
    feasible = [o for o in opts if o.option_id in checks and checks[o.option_id].feasible]
    scored = [(o, cost_j(o.metrics.model_dump(), w)) for o in feasible]
    scored.sort(key=lambda x: (x[1], x[0].eta_shift_min, x[0].option_id))
    ranking = [(o.option_id, j) for o, j in scored]
    if not scored:
        return FallbackResult(status="ESCALATE", option_id=None, cost_J=None, ranking=[], weights=w,
                              reason="no feasible option: diversion candidate")
    best, j = scored[0]
    return FallbackResult(status="PLAN", option_id=best.option_id, cost_J=j, ranking=ranking, weights=w,
                          reason=f"min J among {len(scored)} feasible options")
