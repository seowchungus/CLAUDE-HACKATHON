"""Coordinator: a deterministic state machine (no LLM). R1 PROPOSE -> R2 RESPOND -> R3 BALLOT ->
CONSENSUS | FALLBACK -> human approval. Every event is written to the hash-chained ConsensusLog and
yielded as an SSE envelope (CONTRACTS.md §3). The checker always has the last word.
"""
import asyncio
import os
import time
from typing import AsyncIterator, Literal

from core.config import load_config
from core.log import ConsensusLog, verify_chain
from core.types import CheckReport, FallbackResult, Option, ScenarioBundle
from agents import callcount, killswitch
from core.constraints import check_option
from core.fallback import solve
from core.options import counter_allowed_values, make_option
from agents.narrator import narrate
from agents.prompting import ROLES, RoundState, build_call, phase_of
from agents.schema import MAX_ROUNDS_HARD, AgentMessage, AgentPosition, Counter, ungrounded_numbers

ALL_CONSTRAINTS = ["H1_wake_separation", "H2_runway_capacity", "H3_fuel_reserve", "H4_gate_validity",
                   "H5_crew_duty", "H6_taxiway_reachability", "H7_severe_turbulence"]
_DONE = object()


def default_llm(cfg: dict):
    """GeminiClient when a key exists and MOCK is not set; otherwise the offline mock."""
    from agents.client import GeminiClient, MockLLMClient
    if os.environ.get("MOCK") == "1":
        return MockLLMClient(config=cfg)
    try:
        return GeminiClient(cfg)
    except RuntimeError:
        return MockLLMClient(config=cfg)


class Coordinator:
    def __init__(self, bundle: ScenarioBundle, run_id: str, config: dict | None = None,
                 llm=None, parent_run_id: str | None = None, narrator=None):
        self.cfg = config or load_config()
        self.max_rounds = int(self.cfg["negotiation"]["MAX_ROUNDS"])
        if not 1 <= self.max_rounds <= MAX_ROUNDS_HARD:   # explicit raise: `python -O` strips asserts
            raise ValueError(f"MAX_ROUNDS must be 1..{MAX_ROUNDS_HARD}, got {self.max_rounds}")
        self.bundle = bundle
        self.s = bundle.scenario
        self.run_id = run_id
        self.parent_run_id = parent_run_id
        self.llm = llm if llm is not None else default_llm(self.cfg)
        self.narrator = narrator or (lambda b, evs: narrate(b, evs, llm=self.llm, cfg=self.cfg))
        self.options: list[Option] = list(bundle.options)
        self.checks: dict[str, CheckReport] = dict(bundle.checks)
        self.allowed = counter_allowed_values(self.s)
        self.log = ConsensusLog(run_id, self.s, runs_dir=self.cfg["paths"]["runs_dir"])
        self.envelopes: list[dict] = []
        self.n_llm_calls = 0
        self.rounds_used = 0
        self.decision: dict | None = None        # {source, option_id}
        self.finished = False
        self.approved: dict | None = None
        self._seq = 0
        self._queue: asyncio.Queue | None = None
        self._n_counters = 0
        self._task: asyncio.Task | None = None
        self._cancelling = False
        self._t0 = time.monotonic()

    # ------------------------------------------------------------------ events
    def _emit(self, type_: str, data: dict, actor: str = "COORDINATOR",
              constraint_ids: list[str] | None = None) -> dict:
        entry = self.log.append(type_, actor, data, constraint_ids or [])
        env = {"type": type_, "run_id": self.run_id, "seq": self._seq, "ts": entry.ts,
               "log_hash": entry.hash, "data": entry.payload}
        self._seq += 1
        self.envelopes.append(env)
        if self._queue is not None:
            self._queue.put_nowait(env)
        return env

    def _options_payload(self) -> dict:
        return {"options": [o.model_dump(mode="json") for o in self.options],
                "checks": {k: v.model_dump(mode="json") for k, v in self.checks.items()},
                "fallback": self.bundle.fallback.model_dump(mode="json"),
                "fcfs": self.bundle.fcfs.model_dump(mode="json")}

    def _opt(self, oid: str | None) -> Option | None:
        return next((o for o in self.options if o.option_id == oid), None)

    def _feasible(self, oid: str | None) -> bool:
        return bool(oid) and oid in self.checks and self.checks[oid].feasible

    def _failed(self, oid: str) -> list[str]:
        return [r.constraint_id for r in self.checks[oid].results if not r.passed]

    def _failed_detail(self, oid: str) -> str:
        return "; ".join(r.detail for r in self.checks[oid].results if not r.passed)

    # ------------------------------------------------------------------ public
    async def run(self) -> AsyncIterator[dict]:
        self._queue = asyncio.Queue()
        self._task = asyncio.create_task(self._drive_safe())
        try:
            while True:
                env = await self._queue.get()
                if env is _DONE:
                    break
                yield env
        finally:
            if not self._task.done():
                self._task.cancel()
            self._queue = None

    async def cancel(self, reason: str = "SUPERSEDED") -> bool:
        """Stop in-flight calls and end the run (W3 calls this when chaos starts a child run).
        Returns False if the run had already finished."""
        if self.finished:
            return False
        self._cancelling = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._emit("run_ended", {"final_state": reason, "rounds_used": self.rounds_used,
                                 "latency_ms": int((time.monotonic() - self._t0) * 1000),
                                 "chain_ok": verify_chain(self.log.path).ok, "n_llm_calls": self.n_llm_calls})
        self.finished = True
        if self._queue is not None:
            self._queue.put_nowait(_DONE)
        return True

    async def approve(self, action: Literal["APPROVE", "OVERRIDE"], option_id: str | None, by: str,
                      note: str = "") -> dict:
        """Human sign-off. APPROVE only the decided option; OVERRIDE any feasible option; on ESCALATE
        only OVERRIDE with an explicit feasible option. One approval per run. Errors carry code 409/400."""
        def err(code, msg):
            return {"ok": False, "final_hash": None, "error": msg, "code": code}
        if not self.finished or self.decision is None:
            return err(409, "run has not reached awaiting_approval")
        if self.approved is not None:
            return err(409, "run already approved")
        if action not in ("APPROVE", "OVERRIDE"):
            return err(400, f"unknown action {action}")
        decided = self.decision.get("option_id")
        if self.decision["source"] == "ESCALATE" and action != "OVERRIDE":
            return err(400, "ESCALATE: no automated plan; use OVERRIDE with an explicit option_id")
        if action == "APPROVE" and option_id != decided:
            return err(400, f"APPROVE is only for the decided option {decided}; use OVERRIDE for {option_id}")
        if self._opt(option_id) is None:
            return err(400, f"unknown option {option_id}")
        if not self._feasible(option_id):
            return err(400, f"{option_id} fails {', '.join(self._failed(option_id))}; the checker overrides")
        signed = self.log.head_hash()
        env = self._emit("approved", {"action": action, "option_id": option_id, "by": by, "note": note,
                                      "final_hash": signed}, actor="HUMAN")
        self.approved = env
        return {"ok": True, "final_hash": signed}

    # ------------------------------------------------------------------ state machine
    async def _drive_safe(self):
        t0 = self._t0 = time.monotonic()
        try:
            await self._drive(t0)
        except asyncio.CancelledError:
            return
        except Exception as e:  # noqa: BLE001 - any coordinator bug degrades to the safe fallback
            self._emit("error", {"message": f"{type(e).__name__}: {e}"[:300], "fatal": True}, actor="SYSTEM")
            if self.decision is None:
                self._fallback("LLM_ERROR", use_bundle=True)
            if not self.finished:
                self._finish(t0)
        finally:
            if self._queue is not None and not self._cancelling:
                self._queue.put_nowait(_DONE)

    async def _drive(self, t0: float):
        models = {r: self.cfg["models"][r] for r in (*ROLES, "NARRATOR")}
        self._emit("run_started", {"scenario_id": self.s.scenario_id, "max_rounds": self.max_rounds,
                                   "llm_enabled": killswitch.llm_enabled(), "models": models,
                                   "parent_run_id": self.parent_run_id,
                                   "scripted": bool(getattr(self.llm, "scripted", False)),
                                   "chaos_applied": [c.model_dump(mode="json") for c in self.s.chaos_applied]})
        self._emit("options", self._options_payload(), actor="CHECKER", constraint_ids=ALL_CONSTRAINTS)

        min_calls = len(ROLES) * self.max_rounds
        left = self.llm.budget_remaining() if hasattr(self.llm, "budget_remaining") else None
        if killswitch.llm_enabled() and left is not None and left < min_calls:
            # don't start a negotiation the free-tier budget can't finish
            self._emit("error", {"message": f"LLM budget exhausted ({left} calls left today, a run needs "
                                            f"up to {min_calls}); deterministic fallback", "fatal": False},
                       actor="SYSTEM")
            self._fallback("LLM_ERROR", use_bundle=True)
            await self._narrate()
            self._finish(t0)
            return

        positions: dict[str, AgentPosition] = {}
        counter_results: list[dict] = []
        tentative: str | None = None
        forced_ballot = False
        rnd = 1
        while rnd <= self.max_rounds:
            if not killswitch.llm_enabled():
                self._fallback("LLM_KILLED", use_bundle=True)
                break
            candidates = [o.option_id for o in self.options]
            st = RoundState(round=rnd, candidates=candidates, tentative=tentative,
                            last_positions=dict(positions), counter_results=list(counter_results),
                            phase="BALLOT" if forced_ballot else None)
            phase = phase_of(st, self.max_rounds)
            ballot = phase == "BALLOT"
            self.rounds_used = rnd
            self._emit("round_started", {"round": rnd, "phase": phase, "candidates": candidates,
                                         "tentative": tentative})
            msgs = await self._call_round(st)

            if any(m.status == "killed" for m in msgs) or not killswitch.llm_enabled():
                self._fallback("LLM_KILLED", use_bundle=True)
                break
            if rnd == 1 and all(m.status != "ok" for m in msgs):
                self._fallback("LLM_ERROR")
                break

            now = {m.agent: m.position for m in msgs if m.status == "ok" and m.position}
            prev_positions = dict(positions)
            positions.update(now)

            new_ids: list[str] = []
            if not ballot:
                for m in msgs:
                    if m.agent in now and now[m.agent].counter is not None:
                        res = self._check_counter(rnd, m.agent, now[m.agent].counter)
                        counter_results.append(res)
                        if res["accepted"]:
                            new_ids.append(res["option_id"])
                if new_ids:
                    self._emit("options", self._options_payload(), actor="CHECKER",
                               constraint_ids=ALL_CONSTRAINTS)

            self._vetoes(rnd, now, tentative)

            accepts = {r: (r in now and now[r].action == "ACCEPT") for r in ROLES}
            all_accept = rnd >= 2 and tentative is not None and all(accepts.values())
            agreement, minmax = self._agreement(now, prev_positions, new_ids, tentative)
            if all_accept or ballot:     # the ballot option stays on the table
                new_tent = tentative
            else:
                new_tent = min(agreement, key=lambda o: (minmax[o], self._opt(o).metrics.cost_J, o)) \
                    if agreement else None
            self._emit("tentative", {"round": rnd, "option_id": new_tent, "agreement_set": agreement,
                                     "minmax_rank": {o: minmax[o] for o in sorted(agreement, key=lambda o: (minmax[o], o))}})
            self._emit("round_ended", {"round": rnd, "all_accept": all_accept,
                                       "actions": {r: (now[r].action if r in now else None) for r in ROLES}})

            if all_accept:
                if self._feasible(tentative):
                    self._consensus(rnd, tentative, now)
                else:   # the checker overrides any agreement
                    self._emit("veto", {"round": rnd, "option_id": tentative, "agents": list(ROLES),
                                        "failed": self._failed(tentative),
                                        "reason": f"all agents accepted {tentative} but "
                                                  f"{self._failed_detail(tentative)}; checker overrides"},
                               actor="CHECKER", constraint_ids=self._failed(tentative))
                    self._fallback("NO_CONSENSUS")
                break
            if ballot:
                self._fallback("NO_CONSENSUS")
                break
            if new_tent is None:
                fb = solve(self.s, self.options, self.checks)
                if fb.status == "ESCALATE" or not fb.option_id:
                    self._fallback("NO_FEASIBLE", result=fb)
                    break
                tentative, forced_ballot = fb.option_id, True   # straight to the ballot
            else:
                tentative = new_tent
            rnd += 1

        if self.decision is None:   # loop exhausted without a decision (defensive)
            self._fallback("NO_CONSENSUS")
        await self._narrate()
        self._finish(t0)

    async def _call_round(self, st: RoundState) -> list[AgentMessage]:
        """THREE separate LLM calls, in parallel. Never one call for several roles."""
        calls = {r: build_call(self.s, self.options, self.checks, r, st, self.cfg) for r in ROLES}
        for r in ROLES:
            self._emit("agent_thinking", {"round": st.round, "agent": r})
        with callcount.counting() as n:   # per run, not a delta of a client shared with other runs
            msgs = await asyncio.gather(*(self.llm.position(r, c.prompt, c.response_model, c.round, call=c)
                                          for r, c in calls.items()), return_exceptions=True)
        out = []
        for r, m in zip(ROLES, msgs):
            if isinstance(m, BaseException):
                m = AgentMessage(agent=r, round=st.round, status="error", position=None,
                                 model=self.cfg["models"][r], latency_ms=0,
                                 errors=[f"{type(m).__name__}: {m}"[:200]])
            if m.position is not None:   # grounding: a flag on the logged message, never a rejection
                m.ungrounded = bool(ungrounded_numbers(m.position.rationale, m.position.cites,
                                                       {o.option_id: o for o in self.options}))
            out.append(m)
        self.n_llm_calls += n[0]
        for m in out:
            self._emit("agent_position", m.model_dump(mode="json"), actor=m.agent)
        return out

    def _check_counter(self, rnd: int, agent: str, c: Counter) -> dict:
        base = self._opt(c.base_option)
        payload = {"round": rnd, "agent": agent, "counter": c.model_dump(mode="json"),
                   "accepted": False, "option_id": None, "reason": "", "check": None, "failed": []}
        if base is None:
            payload["reason"] = f"unknown base option {c.base_option}"
        elif c.value not in self.allowed.get(c.param, []):
            payload["reason"] = f"off-grid: {c.param}={c.value!r} not in allowed values"
        else:
            params = {"eta_shift_min": base.eta_shift_min, "gate": base.gate, "fp_adjustment": base.fp_adjustment}
            params[c.param] = c.value
            dup = next((o.option_id for o in self.options
                        if (o.eta_shift_min, o.gate, o.fp_adjustment) == tuple(params.values())), None)
            if dup:
                payload["reason"] = f"duplicate of {dup}"
            else:
                oid = f"opt_c{self._n_counters + 1}"
                try:
                    opt = make_option(self.s, oid, int(params["eta_shift_min"]), str(params["gate"]),
                                      str(params["fp_adjustment"]), source="counter", proposed_by=agent,
                                      parent_option=base.option_id)
                    rep = check_option(self.s, opt)
                except Exception as e:  # noqa: BLE001
                    payload["reason"] = f"could not evaluate counter: {e}"[:200]
                    self._emit("counter_checked", payload, actor="CHECKER")
                    return payload
                payload["check"] = rep.model_dump(mode="json")
                if rep.feasible:
                    self._n_counters += 1
                    self.options.append(opt)
                    self.checks[oid] = rep
                    payload.update(accepted=True, option_id=oid, reason="all hard constraints pass")
                    self._emit("counter_checked", payload, actor="CHECKER", constraint_ids=ALL_CONSTRAINTS)
                    return payload
                failed = [r for r in rep.results if not r.passed]
                payload["failed"] = [r.constraint_id for r in failed]
                payload["reason"] = "; ".join(f"{r.constraint_id}: {r.detail}" for r in failed)[:300]
                self._emit("counter_checked", payload, actor="CHECKER",
                           constraint_ids=[r.constraint_id for r in failed])
                return payload
        self._emit("counter_checked", payload, actor="CHECKER")
        return payload

    def _vetoes(self, rnd: int, now: dict[str, AgentPosition], tentative: str | None):
        """An agent ranked first, or declared acceptable/accepted, an option that fails the checker."""
        flagged: dict[str, dict[str, list[str]]] = {}
        for r in ROLES:
            p = now.get(r)
            if p is None:
                continue
            hits = []
            if p.ranking and p.ranking[0] in self.checks and not self._feasible(p.ranking[0]):
                hits.append((p.ranking[0], "ranked first"))
            for oid in p.acceptable:
                if oid in self.checks and not self._feasible(oid):
                    hits.append((oid, "accepted"))
            if p.action == "ACCEPT" and tentative and tentative in self.checks and not self._feasible(tentative):
                hits.append((tentative, "accepted"))
            for oid, how in hits:
                flagged.setdefault(oid, {}).setdefault(r, [])
                if how not in flagged[oid][r]:
                    flagged[oid][r].append(how)
        for oid, by in flagged.items():
            who = ", ".join(f"{r} {'/'.join(h)}" for r, h in by.items())
            self._emit("veto", {"round": rnd, "option_id": oid, "agents": list(by), "failed": self._failed(oid),
                                "reason": f"{who} {oid} but {self._failed_detail(oid)}; checker overrides"[:300]},
                       actor="CHECKER", constraint_ids=self._failed(oid))

    def _agreement(self, now: dict[str, AgentPosition], prev: dict[str, AgentPosition], new_ids: list[str],
                   tentative: str | None) -> tuple[list[str], dict[str, int]]:
        """A = ∩ acceptable ∩ hard-feasible; minmax rank = worst rank across agents.
        A counter accepted THIS round is provisionally acceptable to an agent that accepts its parent
        (no agent has seen it yet); from the next round on, the agents' own lists decide."""
        candidates = [o.option_id for o in self.options]
        n = len(candidates) + 1
        parent = {oid: self._opt(oid).parent_option for oid in new_ids}
        A = [o for o in candidates if self._feasible(o)]
        ranks: dict[str, int] = {o: 0 for o in candidates}
        for r in ROLES:
            p = now.get(r) or prev.get(r)
            if p is None:
                continue
            acc = set(p.acceptable)
            if p.action == "ACCEPT" and tentative:
                acc.add(tentative)
            acc |= {c for c, par in parent.items() if par in acc or self._opt(c).proposed_by == r}
            A = [o for o in A if o in acc]
            for o in candidates:
                ref = parent.get(o, o)
                rank = (p.ranking.index(o) + 1 if o in p.ranking
                        else p.ranking.index(ref) + 1 if ref in p.ranking else n)
                ranks[o] = max(ranks[o], rank)
        return A, {o: ranks[o] for o in A}

    def _consensus(self, rnd: int, oid: str, now: dict[str, AgentPosition]):
        plan = self._opt(oid)
        self.decision = {"source": "CONSENSUS", "option_id": oid}
        self._emit("consensus", {"round": rnd, "option_id": oid, "plan": plan.model_dump(mode="json"),
                                 "check": self.checks[oid].model_dump(mode="json"),
                                 "accepts": {r: now[r].rationale for r in ROLES}},
                   constraint_ids=ALL_CONSTRAINTS)

    def _fallback(self, reason: str, use_bundle: bool = False, result: FallbackResult | None = None):
        if result is None:
            result = self.bundle.fallback if use_bundle else solve(self.s, self.options, self.checks)
        plan = self._opt(result.option_id) if result.status == "PLAN" else None
        if plan is not None and not self._feasible(plan.option_id):   # never emit an unsafe plan
            plan, result = None, result.model_copy(update={"status": "ESCALATE", "option_id": None,
                                                           "reason": "fallback plan failed the checker"})
        source = "FALLBACK" if plan is not None else "ESCALATE"
        self.decision = {"source": source, "option_id": plan.option_id if plan else None}
        self._emit("fallback", {"reason": reason, "result": result.model_dump(mode="json"),
                                "plan": plan.model_dump(mode="json") if plan else None},
                   actor="FALLBACK", constraint_ids=ALL_CONSTRAINTS if plan else [])

    async def _narrate(self):
        if self.narrator is None:
            return
        try:
            with callcount.counting() as n:   # 0 with the template narrator
                try:
                    text = await self.narrator(self.bundle, list(self.envelopes))
                finally:
                    self.n_llm_calls += n[0]
        except Exception:  # noqa: BLE001 - narration is optional
            return
        if text:
            self._emit("narration", {"text": text}, actor="NARRATOR")

    def _finish(self, t0: float):
        d = self.decision or {"source": "ESCALATE", "option_id": None}
        self._emit("awaiting_approval", {"decision_source": d["source"], "option_id": d["option_id"],
                                         "rounds_used": self.rounds_used})
        chain_ok = verify_chain(self.log.path).ok
        self._emit("run_ended", {"final_state": d["source"], "rounds_used": self.rounds_used,
                                 "latency_ms": int((time.monotonic() - t0) * 1000), "chain_ok": chain_ok,
                                 "n_llm_calls": self.n_llm_calls})
        self.finished = True
