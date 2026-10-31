"""Render the ONE merged template (blocks A–E) and build the per-call response model + validation ctx."""
import os
from dataclasses import dataclass, field

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.config import load_config
from core.metrics import min_turnaround
from core.types import CheckReport, Option, Scenario
from core.options import counter_allowed_values
from agents.charters import charter_for
from agents.schema import (ACTIONS_BY_ROUND, METRIC_NAMES, PHASE_BY_ROUND, AgentPosition, ValidationCtx,
                           build_position_model, metric_refs_for)

ROLES = ("ATC", "PILOT", "GROUND")
ROLE_SPLIT_MARKER = "# Your role:"   # first line of block C; everything before it is the shared prefix

_env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "prompts")),
                   undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
_env.filters["hhmm"] = lambda m: f"{(int(m) // 60) % 24:02d}:{int(m) % 60:02d}"


@dataclass
class RoundState:
    round: int
    candidates: list[str]
    tentative: str | None = None
    last_positions: dict[str, AgentPosition] = field(default_factory=dict)   # role -> latest ok position
    counter_results: list[dict] = field(default_factory=list)                # counter_checked payloads
    phase: str | None = None                                                 # override (e.g. early BALLOT)


@dataclass
class AgentCall:
    role: str
    round: int
    prompt: str
    response_model: type
    ctx: ValidationCtx
    view: dict      # structured data for MockLLMClient (it can't read prompts)


def phase_of(st: RoundState, max_rounds: int) -> str:
    return st.phase or ("BALLOT" if st.round >= max_rounds else PHASE_BY_ROUND[st.round])


def render_prompt(s: Scenario, options: list[Option], checks: dict[str, CheckReport], role: str,
                  st: RoundState, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    max_rounds = cfg["negotiation"]["MAX_ROUNDS"]
    phase = phase_of(st, max_rounds)
    actions = ACTIONS_BY_ROUND[3] if phase == "BALLOT" else ACTIONS_BY_ROUND[min(st.round, 2)]
    r = s.row
    sd = s.model_dump(mode="json")
    return _env.get_template("agent.md.j2").render(
        s=sd,
        date=f"{r.year:04d}-{r.month:02d}-{r.day:02d}",
        max_rounds=max_rounds,
        allowed=counter_allowed_values(s),
        metric_cols=list(METRIC_NAMES),
        options=[o.model_dump(mode="json") for o in options],
        checks={k: v.model_dump(mode="json") for k, v in checks.items()},
        role=role,
        charter=charter_for(role, s.destination.iata, s.disrupted.flight_id),
        wake_sep=cfg["thresholds"]["wake_separation_s"],
        fuel_reserve=cfg["thresholds"]["fuel_final_reserve_min"],
        turb_severe=cfg["thresholds"]["turbulence_severe"],
        min_turn=min_turnaround(s),   # same value core.metrics uses (workbook per airport, else fallback)
        fuel_spare=cfg["thresholds"].get("fuel_spare_on_arrival_min"),
        crew_max_h=round(cfg["thresholds"].get("flight_crew_max_duty_min", 780) / 60, 1),
        gate_notice=cfg["thresholds"].get("gate_change_notice_min"),
        shift_h=round(cfg["thresholds"].get("ground_shift_min", 480) / 60, 1),
        ot_mult=cfg["thresholds"].get("ground_overtime_cost_multiplier"),
        limits=s.airport_limits or {},
        prov=lambda f: (s.provenance.get(f) or "unlabelled").upper(),
        round=st.round, phase=phase, actions=actions,
        candidates=st.candidates, tentative=st.tentative,
        counter_results=st.counter_results,
        others=[p.model_dump(mode="json") for k, p in st.last_positions.items() if k != role],
        own=st.last_positions[role].model_dump(mode="json") if role in st.last_positions else None,
    )


def build_call(s: Scenario, options: list[Option], checks: dict[str, CheckReport], role: str,
               st: RoundState, cfg: dict | None = None) -> AgentCall:
    cfg = cfg or load_config()
    max_rounds = cfg["negotiation"]["MAX_ROUNDS"]
    ballot = phase_of(st, max_rounds) == "BALLOT"
    option_ids = [o.option_id for o in options]
    refs = metric_refs_for(option_ids)
    allowed = counter_allowed_values(s)
    model = build_position_model(st.candidates, metric_refs_for(st.candidates), st.round,
                                 agent=role, max_rounds=max_rounds, ballot=ballot)
    ctx = ValidationCtx(agent=role, round=st.round, candidates=list(st.candidates), option_ids=option_ids,
                        metric_refs=refs, allowed_values=allowed, tentative=st.tentative,
                        max_rounds=max_rounds, ballot=ballot)
    view = {"scenario": s, "options": {o.option_id: o for o in options}, "checks": checks,
            "candidates": list(st.candidates), "tentative": st.tentative, "allowed": allowed,
            "ballot": ballot}
    return AgentCall(role=role, round=st.round, prompt=render_prompt(s, options, checks, role, st, cfg),
                     response_model=model, ctx=ctx, view=view)
