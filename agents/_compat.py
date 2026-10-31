"""Thin adapter until W1's core is complete. DELETE AT INTEGRATION once core.options,
core.constraints and core.fallback exist (each function below prefers the real one).

The stubs never invent metrics for an LLM: they reuse fixture metrics and only re-derive the few
fields a one-parameter counter changes, and they are used only while the real core is missing.
"""
import json

from core.config import load_config, repo_path
from core.types import CheckReport, ConstraintResult, FallbackResult, Option, Scenario, ScenarioBundle

try:
    from core.options import counter_allowed_values as _core_allowed, make_option as _core_make_option
except ImportError:  # pragma: no cover - depends on W1 progress
    _core_allowed = _core_make_option = None
try:
    from core.constraints import check_option as _core_check_option
except ImportError:  # pragma: no cover
    _core_check_option = None
try:
    from core.fallback import solve as _core_solve
except ImportError:  # pragma: no cover
    _core_solve = None

FIXTURE_BUNDLE = "docs/fixtures/scenario_bundle.json"


def load_bundle(path: str = FIXTURE_BUNDLE) -> ScenarioBundle:
    with open(repo_path(path), encoding="utf-8") as f:
        data = json.load(f)
    return ScenarioBundle.model_validate(data.get("bundle", data))


def counter_allowed_values(s: Scenario) -> dict[str, list]:
    if _core_allowed:
        return _core_allowed(s)
    cfg = load_config()
    return {"eta_shift_min": list(cfg["options"]["eta_shifts_min"]),
            "gate": [g.gate_id for g in s.gates],
            "fp_adjustment": list(cfg["options"]["fp_adjustments"])}


def make_option(s: Scenario, option_id: str, eta_shift_min: int, gate: str, fp: str,
                source: str = "generated", proposed_by=None, parent_option=None,
                known: list[Option] | None = None) -> Option:
    if _core_make_option:
        return _core_make_option(s, option_id, eta_shift_min, gate, fp, source=source,
                                 proposed_by=proposed_by, parent_option=parent_option)
    # stub: reuse metrics of the closest known option, re-derive what the counter changed
    known = known or []
    base = next((o for o in known if o.option_id == parent_option), known[0])
    m = base.metrics.model_copy()
    m.gate = gate
    m.eta_new_min = s.base_eta_min + eta_shift_min
    m.turbulence_idx = s.turbulence_by_fp.get(fp, m.turbulence_idx)
    g = next((g for g in s.gates if g.gate_id == gate), None)
    if g:
        m.taxi_path_ok = not set(g.taxi_path) & set(s.blocked_taxiways)
    fp_label = fp.replace("_", " ")
    return Option(option_id=option_id, eta_shift_min=eta_shift_min, gate=gate, fp_adjustment=fp,
                  source=source, proposed_by=proposed_by, parent_option=parent_option,
                  label=f"+{eta_shift_min} min, gate {gate}, {fp_label}", metrics=m)


def check_option(s: Scenario, opt: Option, base_check: CheckReport | None = None) -> CheckReport:
    if _core_check_option:
        return _core_check_option(s, opt)
    # stub: inherit the parent's results, recheck H4 (gate occupancy) / H6 / H7
    cfg = load_config()
    results = [r.model_copy(update={"option_id": opt.option_id}) for r in base_check.results]
    m = opt.metrics
    g = next((g for g in s.gates if g.gate_id == opt.gate), None)
    end = (s.next_departure_min or m.eta_new_min + 60)
    busy = g is None or g.out_of_service or any(a < end and m.eta_new_min < b for a, b in g.occupied)
    for i, r in enumerate(results):
        if r.constraint_id == "H4_gate_validity":
            if busy and g is not None:
                spans = ", ".join(f"{a // 60:02d}:{a % 60:02d}-{b // 60:02d}:{b % 60:02d}" for a, b in g.occupied)
                detail = f"gate {opt.gate} occupied {spans} by another aircraft"
            else:
                detail = "gate free and size-compatible" if not busy else f"unknown gate {opt.gate}"
            results[i] = ConstraintResult(option_id=opt.option_id, constraint_id=r.constraint_id,
                                          passed=not busy, value=None, threshold=None, detail=detail[:120])
        elif r.constraint_id == "H6_taxiway_reachability":
            results[i] = r.model_copy(update={"passed": m.taxi_path_ok,
                                              "detail": "taxi path clear" if m.taxi_path_ok else "taxi path blocked"})
        elif r.constraint_id == "H7_severe_turbulence":
            thr = cfg["thresholds"]["turbulence_severe"]
            results[i] = r.model_copy(update={"passed": m.turbulence_idx < thr, "value": m.turbulence_idx,
                                              "threshold": thr,
                                              "detail": f"turbulence {m.turbulence_idx} vs severe {thr}"})
    return CheckReport(option_id=opt.option_id, feasible=all(r.passed for r in results), results=results)


def solve(s: Scenario, opts: list[Option], checks: dict[str, CheckReport]) -> FallbackResult:
    if _core_solve:
        return _core_solve(s, opts, checks)
    weights = load_config()["fallback_weights"]
    feas = sorted(((o.option_id, o.metrics.cost_J) for o in opts
                   if checks.get(o.option_id) and checks[o.option_id].feasible), key=lambda t: (t[1], t[0]))
    if not feas:
        return FallbackResult(status="ESCALATE", option_id=None, cost_J=None, ranking=[], weights=weights,
                              reason="no feasible option: diversion candidate")
    return FallbackResult(status="PLAN", option_id=feas[0][0], cost_J=feas[0][1], ranking=feas,
                          weights=weights, reason=f"min J among {len(feas)} feasible options")
