"""ScenarioBundle assembly: scenario + options + checks (incl. opt_fcfs) + shadow fallback + FCFS baseline."""
from core.constraints import check_all
from core.fallback import fcfs, solve
from core.options import generate_options
from core.scenario import build_scenario
from core.types import ChaosEvent, Scenario, ScenarioBundle


def build_bundle_from_scenario(s: Scenario) -> ScenarioBundle:
    opts = generate_options(s)
    base = fcfs(s)
    checks = check_all(s, opts + [base])
    return ScenarioBundle(scenario=s, options=opts, checks=checks, fallback=solve(s, opts, checks), fcfs=base)


def build_bundle(scenario_id: str, chaos: list[ChaosEvent] | None = None) -> ScenarioBundle:
    s = build_scenario(scenario_id)
    if chaos:
        from core.chaos import apply_chaos
        for ev in chaos:
            s = apply_chaos(s, ev)
    return build_bundle_from_scenario(s)
