"""Narrator (proposal §4.4, §6): a <=120-word plain-English summary for the duty manager, and the
one-page Resolution Record. It only restates numbers that already appear in the events; it never
computes or decides. With `models.narrator_llm: false` (or no LLM / kill switch) it uses a template.
"""
from core.config import load_config
from core.types import ScenarioBundle
from agents import killswitch

MAX_WORDS = 120


def _hhmm(m) -> str:
    return f"{(int(m) // 60) % 24:02d}:{int(m) % 60:02d}"


def _of(events: list[dict], t: str) -> list[dict]:
    return [e["data"] for e in events if e["type"] == t]


def _decision(events: list[dict]) -> tuple[str, dict | None, dict]:
    """(source, plan, decision payload)."""
    for e in events:
        if e["type"] == "consensus":
            return "CONSENSUS", e["data"]["plan"], e["data"]
        if e["type"] == "fallback":
            d = e["data"]
            return ("FALLBACK" if d["plan"] else "ESCALATE"), d["plan"], d
    return "ESCALATE", None, {}


def template_narration(bundle: ScenarioBundle, events: list[dict]) -> str:
    s = bundle.scenario
    src, plan, d = _decision(events)
    head = (f"{s.disrupted.flight_id} {s.origin.iata}-{s.destination.iata}, delayed {s.disruption_min} min "
            f"({s.disruption_type.replace('_', ' ').lower()}).")
    if plan is None:
        body = ("No option passed every hard constraint, so there is no safe automated plan. "
                "The duty manager must decide; diversion is a candidate.")
    else:
        m = plan["metrics"]
        how = (f"All three agents agreed in round {d['round']} on" if src == "CONSENSUS"
               else f"The agents did not agree ({d.get('reason', '')}), so the deterministic optimiser chose")
        body = (f"{how} {plan['label']}: landing {_hhmm(m['eta_new_min'])} at gate {plan['gate']}, "
                f"{m['misconnected_pax']} misconnected passengers, {m['fuel_at_landing_min']} min fuel at landing, "
                f"{m['ramp_overtime_min']} min ramp overtime, {m['bank_delay_added_min']} min added to other arrivals. "
                f"It passes all seven hard constraints.")
    vetoes = _of(events, "veto")
    rejected = [c for c in _of(events, "counter_checked") if not c["accepted"]]
    extra = []
    if vetoes:
        extra.append(f"The checker vetoed {len(vetoes)} unsafe choice{'s' if len(vetoes) > 1 else ''} "
                     f"({', '.join(sorted({v['option_id'] for v in vetoes}))}).")
    if rejected:
        extra.append(f"{len(rejected)} counter-proposal{'s were' if len(rejected) > 1 else ' was'} rejected.")
    text = " ".join([head, body, *extra, "Awaiting your approval."])
    words = text.split()
    return " ".join(words[:MAX_WORDS])


async def narrate(bundle: ScenarioBundle, events: list[dict], llm=None, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    fallback = template_narration(bundle, events)
    if not cfg["models"].get("narrator_llm") or llm is None or not hasattr(llm, "text") \
            or not killswitch.llm_enabled():
        return fallback
    src, plan, d = _decision(events)
    facts = {"flight": bundle.scenario.disrupted.flight_id, "decision": src, "plan": plan,
             "vetoes": _of(events, "veto"), "rejected_counters": [c for c in _of(events, "counter_checked")
                                                                   if not c["accepted"]]}
    prompt = (f"Summarise this disruption resolution for an airline duty manager in at most {MAX_WORDS} words of "
              "plain English. Only use numbers that appear in the facts. Do not calculate. Do not recommend.\n"
              f"Facts (JSON): {facts}\nTemplate summary for reference: {fallback}")
    try:
        text, _ = await llm.text("NARRATOR", prompt)
    except Exception:  # noqa: BLE001
        return fallback
    words = (text or "").split()
    return " ".join(words[:MAX_WORDS]) if words else fallback


def record_markdown(bundle: ScenarioBundle, events: list[dict], log_head: str) -> str:
    """One-page Resolution Record (served by W3 at /api/runs/{id}/record)."""
    s = bundle.scenario
    prov = s.provenance
    tag = lambda f: "SYNTHETIC" if prov.get(f) == "synthetic" else (prov.get(f) or "real").upper()  # noqa: E731
    src, plan, d = _decision(events)
    started = next((e for e in events if e["type"] == "run_started"), None)
    ended = next((e["data"] for e in events if e["type"] == "run_ended"), {})
    narration = next((e["data"]["text"] for e in events if e["type"] == "narration"), None)
    r = s.row
    L = [f"# Resolution Record: {s.disrupted.flight_id} {s.origin.iata}→{s.destination.iata} ({r.year:04d}-{r.month:02d}-{r.day:02d})",
         "",
         f"- Run: `{started['run_id'] if started else '?'}`  ·  Scenario: `{s.scenario_id}`"
         + ("  ·  **SCRIPTED agents (mock)**" if started and started["data"].get("scripted") else ""),
         f"- Source DOT row (REAL): WEATHER_DELAY {r.weather_delay} min, LATE_AIRCRAFT_DELAY {r.late_aircraft_delay} min, "
         f"ARRIVAL_DELAY {r.arrival_delay} min",
         f"- Delayed ETA {_hhmm(s.base_eta_min)} [{tag('base_eta_min')}]; reduced AAR {s.aar_reduced}/h [{tag('aar_reduced')}]; "
         f"fuel at fix {s.fuel_at_fix_min} min [{tag('fuel_at_fix_min')}]; ramp shift ends {_hhmm(s.ramp_shift_end_min)} "
         f"[{tag('ramp_shift_end_min')}]",
         f"- Decision source: **{src}**  ·  rounds used: {ended.get('rounds_used', '?')}  ·  "
         f"LLM calls: {ended.get('n_llm_calls', '?')}  ·  final state: {ended.get('final_state', '?')}",
         ""]
    L.append("## Plan")
    if plan:
        m = plan["metrics"]
        L += [f"**{plan['option_id']}**: {plan['label']}", "",
              "| metric | value |", "|---|---|"]
        L += [f"| {k} | {m[k]} |" for k in ("eta_new_min", "fuel_at_landing_min", "misconnected_pax",
                                             "ramp_overtime_min", "turnaround_buffer_min", "bank_delay_added_min",
                                             "separation_margin_s", "cost_J") if k in m]
    else:
        L.append("No safe automated plan (ESCALATE). The duty manager decides; diversion is a candidate.")
    if narration:
        L += ["", f"> {narration}"]
    L += ["", "## Agent positions"]
    if src == "CONSENSUS":
        L += [f"- **{a}** accepted: {why}" for a, why in d["accepts"].items()]
    else:
        last = {}
        for p in _of(events, "agent_position"):
            last[p["agent"]] = p
        for a, p in last.items():
            pos = p.get("position")
            L.append(f"- **{a}** (round {p['round']}, {p['status']}): "
                     + (f"{pos['action']}: {pos['rationale']}" if pos else "; ".join(p.get("errors", [])) or "no answer"))
    check = d.get("check") if src == "CONSENSUS" else None
    if check:
        L += ["", "## Constraint checks (plan)"]
        L += [f"- {'PASS' if c['passed'] else 'FAIL'} {c['constraint_id']}: {c['detail']}" for c in check["results"]]
    vetoes = _of(events, "veto")
    rejected = [c for c in _of(events, "counter_checked") if not c["accepted"]]
    if vetoes or rejected:
        L += ["", "## Blocked by the checker"]
        L += [f"- Veto R{v['round']} {v['option_id']} ({', '.join(v['agents'])}): {v['reason']}" for v in vetoes]
        L += [f"- Counter R{c['round']} {c['agent']} {c['counter']['param']}={c['counter']['value']}: {c['reason']}"
              for c in rejected]
    L += ["", "## Audit", f"- Log chain head: `{log_head}`  ·  chain verified: {ended.get('chain_ok', '?')}",
          "- Synthetic fields are simulated; separation and fuel rules are simplified illustrations, not certified values."]
    return "\n".join(L) + "\n"
