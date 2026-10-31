# ACCORD — Autonomous Cross-domain Coordination for Operational Resolution of Disruptions

**Autonomous SG 2026 · AI & Aerospace Track · Airbus Challenge #2**
*"How might AI help air traffic controllers, pilots and ground operations staff make faster and better decisions?"*

> **Three agents. Three rounds. One safe plan.**
> When a flight is disrupted, ACCORD gives three independent AI agents (ATC, Pilot, Ground Ops) their own domain data. They negotiate a revised arrival time, gate and flight-plan adjustment under hard safety constraints enforced by code, with no human in the loop until they reach consensus. The duty manager then approves one plan with a full, tamper-evident audit trail.

---

## 1. The product

### 1.1 What ACCORD is

ACCORD is a **disruption resolution console** for an airline operations or airport operations centre. It has three parts:

1. **A negotiation engine.** Three LLM agents, each in its own API call with its own role, goals and private data, exchange structured messages through a deterministic coordinator. The coordinator enforces a hard limit of 3 rounds.
2. **A safety layer.** A pure-Python constraint checker validates every proposal against hard operational rules: wake separation, fuel reserve, gate availability, taxiway blockage and crew duty. A deterministic optimiser takes over if the agents can't agree, or if the AI is unavailable.
3. **An ops console.** A live web UI where you can watch the negotiation stream, see the disrupted flight and the competing traffic on a US map, see each option light up green or red against every constraint, inject new disruptions ("chaos" events), and approve the final plan.

### 1.2 Who uses it (problem realism)

| | |
|---|---|
| **Primary user** | Airline Operations Control (AOC) duty manager at a hub |
| **Other stakeholders represented by agents** | ATC arrival flow / tower supervisor, flight crew / dispatch, ramp & gate control |
| **Status quo** | When a weather delay or late inbound aircraft hits, these three parties coordinate by phone, radio and manual system updates. Each optimises its own domain, so trade-offs (fuel vs. slot vs. gate vs. crew overtime) are negotiated serially and slowly. Delays cascade, aircraft hold airborne and burn fuel, and passengers misconnect. |
| **Cost evidence** | Computed from the provided 2015 DOT dataset at build time: number of qualifying flights and total `WEATHER_DELAY` + `LATE_AIRCRAFT_DELAY` minutes (see §8.1). No unsourced industry statistics. |
| **What changes** | Resolution in seconds instead of a chain of calls. One consensus plan with every trade-off and constraint check logged. The human approves rather than brokers. |

### 1.3 How it maps to the challenge spec

| Challenge requirement | Where ACCORD meets it |
|---|---|
| ATC, Pilot and Ground agents negotiate without human intervention until consensus | §4 negotiation protocol. Human approval only after the consensus / fallback state (§4.4) |
| ATC: runway wake separation, taxiway blockage, maximise sector throughput | ATC charter + hard constraints H1, H2, H6 + throughput metric (§5) |
| Pilot: fuel reserves, flight safety, minimise turbulence, protect connections | Pilot charter + H3, H7 + turbulence and misconnect metrics |
| Ground: gate utilisation, avoid crew overtime, minimise turnaround delays | Ground charter + H4, H5 + overtime and turnaround metrics |
| Structured messages | Pydantic schema enforced via Gemini's JSON-schema structured output (§4.2) |
| Explicit constraint checking | Deterministic checker on every option and every counter-proposal (§5) |
| Traceable consensus log | Hash-chained JSONL log, viewable and downloadable (§6) |
| Deterministic non-AI fallback | Weighted lexicographic optimiser (§5.3) plus a live "kill the LLM" switch |
| Avoid: 3 roles in a single prompt call | Three separate API calls per round, run in parallel (§3) |
| Avoid: endless loops, no convergence logic | Coordinator is a code state machine with `MAX_ROUNDS = 3`, a final round that is ballot-only, and per-call timeouts (§4.3) |
| Avoid: disregarding safety margins | Agents cannot accept a plan that fails a hard constraint. The checker overrides any agreement (§5.1) |
| Use a DOT 2015 row with `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`, pass its parameters to the agents | Scenario builder (§2) |
| Negotiate revised arrival time, gate assignment or flight plan adjustment in under 3 turns | Every option is a bundle of all three. Headline metric: % resolved by round 2 (§4.3, §8) |

---

## 2. Data and scenario construction

### 2.1 Source

The **US DOT 2015 Flight Delays and Cancellations** dataset (`flights.csv`, `airlines.csv`, `airports.csv`), from `Challenge #2\DATA`.

Fields we use from `flights.csv`: `YEAR, MONTH, DAY, AIRLINE, FLIGHT_NUMBER, TAIL_NUMBER, ORIGIN_AIRPORT, DESTINATION_AIRPORT, SCHEDULED_DEPARTURE, DEPARTURE_DELAY, SCHEDULED_ARRIVAL, ARRIVAL_DELAY, DISTANCE, SCHEDULED_TIME, AIR_TIME, TAXI_IN, TAXI_OUT, WEATHER_DELAY, LATE_AIRCRAFT_DELAY, AIR_SYSTEM_DELAY, DIVERTED, CANCELLED`.

**Pre-processing (once, at minute 0):**
- The file is large (millions of rows), so load it with Polars.
- Keep rows where `WEATHER_DELAY > 15 OR LATE_AIRCRAFT_DELAY > 20` and that are not cancelled or diverted.
- Write the result to `data/qualifying.parquet`, plus a per-day arrivals/departures index.
- **Known quirk to verify:** in some copies of this dataset, October airport codes are numeric IDs instead of IATA codes. Filter those out or map them.

### 2.2 The scenario builder

The single row gives one flight's disruption. Negotiation needs surrounding context, so we build it from **real data first, synthetic second**:

| Context | Source | Real / synthetic |
|---|---|---|
| Disrupted flight: route, schedule, delay type and minutes | The selected row | **Real** |
| Arrival bank (competing traffic for the runway) | All flights into `DESTINATION_AIRPORT` on the same date, `SCHEDULED_ARRIVAL` ±90 min | **Real** |
| Airport coordinates (for the map) | `airports.csv`: `LATITUDE`, `LONGITUDE` per IATA code | **Real** |
| Aircraft position along its route (map animation) | Interpolated along the great-circle arc from scheduled/actual departure and arrival times | Estimated |
| Nominal arrival rate (AAR) | Peak observed hourly arrivals at that airport that day | **Real-derived** |
| Weather-reduced AAR | Nominal AAR × factor based on `WEATHER_DELAY` severity | Synthetic rule |
| Connecting flights at risk | Real departures from `DESTINATION_AIRPORT` by the **same airline**, 30–150 min after scheduled arrival | **Real** |
| Connecting passenger counts | Seeded random per connection | Synthetic |
| Wake category (Heavy / Medium / Light) per aircraft | Heuristic from distance + seeded random | Synthetic |
| Fuel on board at the arrival fix (minutes) | Seeded around a plausible planned value | Synthetic |
| Gate pool, gate size class, taxiway map | Small per-airport template (e.g. 3 concourses, 12 gates, 4 taxiways) | Synthetic |
| Ramp crew shift end, flight crew duty remaining | Seeded | Synthetic |
| Turbulence index per route option | Seeded per scenario | Synthetic |

All randomness is seeded by `(date, airline, flight_number)`, so every scenario is reproducible. **Every synthetic field carries a `synthetic: true` flag in the UI and in the log** (needed for the Honest Evaluation criterion).

### 2.3 Disruption types

1. **From the row (default):** weather delay or late inbound aircraft. The ETA slips, and the runway, gate and connections all have to be re-planned.
2. **Chaos injector (live demo):** runway closure (AAR halved), taxiway blockage (some gates become unreachable), gate equipment failure (one gate unavailable for N min), extra weather cell (+turbulence, +delay). These match the disruptions named in the challenge description.

---

## 3. LLM selection per agent

| Component | Model (API string) | Why |
|---|---|---|
**The whole system runs on free-tier models** (Google Gemini API, no billing account). That is possible because the LLMs never do the safety-critical work: they rank a short table of pre-computed options and explain why.

| Component | Model | Why |
|---|---|---|
| **ATC agent** | Gemini 3.8 Flash | Multi-aircraft trade-offs and throughput reasoning. Fast, free, supports JSON-schema output. |
| **Pilot agent** | Gemini 3.8 Flash | Weighs fuel vs. connections vs. turbulence. Same model as ATC on purpose (see below). |
| **Ground agent** | Gemini 3.8 Flash | Weighs gate, crew and turnaround. Same model, same reason. |
| **Narrator** (plain-English summary for the duty manager after resolution) | Gemini Flash-Lite | A reading and explanation task: cheapest and fastest. Never makes decisions. |
| **Backup / ablation** | Gemini 3.6 Flash, or Gemma 4 | Used if 3.8 Flash hits its rate limit, and to measure how much model capability changes consensus rate. |
| Coordinator, metrics, constraint checker, fallback | **No LLM.** Pure Python. | The rubric rewards LLMs for reading and negotiation, and solvers or rules for constraints and arithmetic. |

**Why the same model for all three negotiators:** if one agent runs on a stronger model, it tends to win negotiations through better argument rather than better operational merit. Model parity keeps the outcome a function of domain constraints. Model choice is set per agent in `config.yaml`, so the stack is not tied to one vendor (a paid model can be swapped in with one line).

**Settings:** temperature 0.2 for negotiators, **JSON-schema structured output** (`response_mime_type: application/json` with the `AgentPosition` schema), 20 s timeout per call, 1 retry on schema failure, exponential back-off on HTTP 429 (rate limit).

**Free-tier constraints and how we handle them:**
- Free-tier limits are low per minute and per day and vary by model; check the project's quota in Google AI Studio at minute 0.
- A live scenario is at most 9 calls (3 agents × 3 rounds), which is fine for the demo.
- The batch evaluation is the heavy part, so each teammate runs a share of it on their own API key/project, and two hero scenarios are pre-recorded as demo insurance.
- On the free tier Google may use prompts to improve its products. Acceptable here: inputs are public 2015 data plus synthetic fields.

---

## 4. Negotiation design

### 4.1 Prompt architecture: "merge the template, never merge the call"

The challenge explicitly forbids combining the three roles in one prompt call. We still merge everything that *can* be shared. **One template renders all three agents.** It is built from layered blocks, with the shared blocks first so they form a common cacheable prefix:

```
┌──────────────────────────────────────────────┐
│ A. Shared protocol   (all agents, all runs)   │ ← cache breakpoint 1
│    rules of engagement, message schema,       │
│    turn limits, "never compute, cite metrics" │
├──────────────────────────────────────────────┤
│ B. Shared scenario brief (all agents, 1 run)  │ ← cache breakpoint 2
│    the DOT row, airport, options + metrics,   │
│    hard-constraint results per option         │
├──────────────────────────────────────────────┤
│ C. Role charter      (per agent, static)      │  ATC / PILOT / GROUND
│ D. Private domain view (per agent, per run)   │  e.g. only Ground sees crew shifts
│ E. Round state       (per agent, per round)   │  others' last positions, tentative plan
└──────────────────────────────────────────────┘
```

- **What this gives us:** one file (`prompts/agent.md.j2`) to maintain, one output schema, identical rules for every agent, and a shared prefix (blocks A+B) that is re-sent 9 times per scenario (3 agents × 3 rounds). Keeping it identical and first lets the API's context caching apply where the model supports it, which cuts tokens and latency.
- **What stays separate:** each agent's charter, its private data and its own API call. Agents only see each other's *structured positions*, never each other's private views. That separation is what makes this real cross-domain negotiation rather than one model role-playing three people.

**Role charters (block C, abridged):**

> **ATC** — You represent arrival flow control at {airport}. Your goals: (1) never violate wake separation or runway capacity, (2) never route an aircraft to a gate whose taxi path is blocked, (3) maximise arrivals handled this hour and minimise knock-on delay to other flights in the bank. You may not trade safety for anything.
>
> **PILOT** — You represent the flight crew of {flight}. Your goals: (1) land with at least final reserve fuel, (2) avoid severe turbulence, (3) minimise misconnected passengers, (4) prefer absorbing delay en route (speed reduction) over airborne holding.
>
> **GROUND** — You represent ramp and gate control at {airport}. Your goals: (1) assign a gate that is free, size-compatible and reachable, (2) avoid ramp crew overtime, (3) protect the turnaround time of the aircraft's next departure.
>
> **All agents (block A):** Every number you mention must come from the metrics table. Cite it as `opt_id.metric`. Do not calculate. You may propose a counter only by changing ONE parameter of an existing option, from the allowed values.

### 4.2 Message schema

Agents respond **only** with JSON matching this schema (passed to Gemini as the response schema):

```python
class Counter(BaseModel):
    base_option: OptionId                      # must exist
    param: Literal["eta_shift_min", "gate", "fp_adjustment"]
    value: str | int                           # must be in the allowed grid

class AgentPosition(BaseModel):
    agent: Literal["ATC", "PILOT", "GROUND"]
    round: Literal[1, 2, 3]
    action: Literal["PROPOSE", "COUNTER", "ACCEPT", "REJECT"]
    ranking: list[OptionId]                    # best first, subset of candidates
    acceptable: list[OptionId]                 # options this agent can live with
    counter: Counter | None                    # only allowed in rounds 1–2
    red_lines: list[ConstraintId]              # e.g. ["H3_fuel_reserve"]
    cites: list[MetricRef]                     # e.g. ["opt_3.fuel_at_landing_min"]
    rationale: constr(max_length=300)
```

Validation is enforced by code, not by trusting the model:
- `OptionId` and `MetricRef` are **enums built per scenario**, so an agent cannot reference a gate or option that doesn't exist.
- A counter in round 3 is rejected.
- **Grounding check (stretch):** numbers in `rationale` must match a cited metric value. If they don't, the message is flagged `ungrounded` in the log.

### 4.3 Protocol: a coordinator state machine (no LLM)

```
INIT ──► R1_PROPOSE ──► R2_RESPOND ──► R3_BALLOT ──► CONSENSUS ──► HUMAN_APPROVAL
                │              │              │
                └──────────────┴──────────────┴──► FALLBACK ──► HUMAN_APPROVAL
```

| Round | Agents (3 parallel calls) | Coordinator (deterministic) |
|---|---|---|
| **R1 Propose** | Rank candidates, declare the acceptable set and red lines, optional counter | Validate schema → run checker on counters → compute metrics for valid counters and add them as new options → **A = ∩ acceptable ∩ hard-feasible** → tentative = option in A with best min-max rank (lowest worst-case rank across agents) |
| **R2 Respond** | See the other agents' structured positions + tentative. ACCEPT, or REJECT/COUNTER with a reason | If all ACCEPT → **CONSENSUS (round 2)**. Otherwise recompute A and choose a new tentative |
| **R3 Ballot** | ACCEPT / REJECT only, on one option. No counters. | All ACCEPT → **CONSENSUS (round 3)**. Otherwise → **FALLBACK** |

**Convergence guarantees:**
- `MAX_ROUNDS = 3` is enforced in code.
- The option set can only grow by validated one-parameter counters in R1–R2.
- R3 cannot introduce anything new.
- A timeout, or a second schema failure, counts as REJECT.
- The worst-case runtime is bounded: 3 rounds × the slowest call.

**"Under 3 turns":** a turn is one round in which all three agents speak. The headline metric is **% of scenarios reaching consensus by round 2**, and round 3 is a pure ballot. `MAX_ROUNDS` is configurable if the organisers read the rule as stricter.

### 4.4 Human in control

No human acts during negotiation (as the challenge specifies). After CONSENSUS or FALLBACK, the duty manager sees:
- the chosen plan
- the reason for each agent's acceptance
- every constraint check
- whether the plan came from consensus or fallback

They can **Approve** or **Override**. Both actions are logged. ACCORD never claims to replace expert judgement.

---

## 5. Options, metrics and constraints (all deterministic)

### 5.1 Option generator

Each **option** is a bundle covering all three negotiable dimensions named in the challenge:
- **Revised arrival time:** `eta_shift_min ∈ {0, 5, 10, …, 60}`, snapped to free runway slots at the reduced AAR
- **Gate assignment:** any gate in the pool
- **Flight plan adjustment:** `as_filed | speed_reduction | hold_N_min | reroute_weather`

The full grid is pruned to **6–8 candidates**: the Pareto front on (delay, fuel, misconnects, overtime), plus at least one option that each agent is likely to prefer. This keeps the set diverse and gives real tension.

**Metrics computed per option** (code only):
`eta_new, runway_slot, separation_margin_s, fuel_at_landing_min, hold_min, turbulence_idx, misconnected_pax, gate, gate_free_from/to, taxi_path_ok, turnaround_buffer_min, ramp_overtime_min, bank_delay_added_min, arrivals_this_hour`

### 5.2 Hard constraints (non-negotiable; the checker overrides any agreement)

| ID | Constraint | Domain | Rule (simplified, labelled as such) |
|---|---|---|---|
| H1 | Wake separation | ATC | Time gap to the preceding arrival ≥ minimum for the (leader, follower) wake category, e.g. Heavy→Light 180 s, Heavy→Medium 120 s, otherwise 60–90 s |
| H2 | Runway capacity | ATC | Arrivals in the hour ≤ reduced AAR |
| H3 | Fuel reserve | Pilot | Fuel at landing ≥ 30 min final reserve |
| H4 | Gate validity | Ground | Gate free across the occupancy window, and size-compatible |
| H5 | Crew duty | Ground/Pilot | Flight crew duty remaining ≥ 0. Ramp overtime ≤ hard cap (soft below the cap) |
| H6 | Taxiway reachability | ATC/Ground | The gate's taxi path avoids blocked taxiways |
| H7 | Severe turbulence | Pilot | `turbulence_idx < severe threshold` |

The wake and fuel values are **illustrative simplifications, not ICAO or certified values**, and the README says so.

### 5.3 Deterministic fallback (also the evaluation baseline)

1. Filter to hard-feasible options.
2. Minimise the weighted cost:
   `J = w_d·bank_delay_added + w_f·extra_fuel_min + w_c·misconnected_pax + w_o·ramp_overtime + w_t·turbulence_idx + w_q·throughput_loss`
   The weights live in `config.yaml` and are shown in the UI.
3. If no option is feasible, the result is **ESCALATE**: there is no safe automated plan, the human decides, and diversion is flagged as a candidate.

The fallback runs **in shadow on every scenario**, so we can always compare LLM consensus against it.

---

## 6. Traceable consensus log

- Every event goes to an append-only JSONL file: scenario load, option set, each agent message, checker results, coordinator decisions, fallback, human approval.
- Each entry stores `prev_hash` and `hash = SHA-256(prev_hash + entry)`. The result is a **tamper-evident chain**, and the UI shows a "chain verified ✓" badge.
- Each entry is timestamped and references the source DOT row (date, airline, flight number) and the constraint IDs applied. That covers the rubric's trust-and-traceability items: timestamped signal and applied rule.
- Export: `.jsonl` for machines, and a one-page "Resolution Record" written by the narrator for humans.

---

## 7. The demo: what judges see

**Ops console (single page):**

1. **Scenario bar:** the real DOT flight (e.g. `AA 1234 DFW→ORD, WEATHER_DELAY 48 min`), with synthetic fields tagged.
2. **Traffic map:** a US map built from `airports.csv` coordinates. The disrupted flight's route is highlighted, the arrival bank's routes converge on the destination, and the at-risk connections fan out as dashed lines. Aircraft markers move along their arcs (positions estimated from schedule times). On a chaos event the destination ring turns amber and the delayed flight's arc and ETA update.
3. **Negotiation room:** three columns (ATC / Pilot / Ground), each streaming its position cards live. A round tracker shows `R1 → R2 → R3`.
4. **Constraint wall:** a grid of options × H1–H7 in green/red. Cells flip as counters arrive. A counter rejected by the checker shakes red with its reason.
5. **Runway and gate timelines:** an SVG Gantt of runway slots for the arrival bank, and gate occupancy. The tentative plan is highlighted, and conflicts glow.
6. **Chaos button:** inject a runway closure, taxiway blockage or gate failure mid-demo, and watch the agents re-negotiate.
7. **"Kill the LLM" switch:** simulates an API outage. ACCORD falls back to the deterministic plan instantly, and the plan stays safe.
8. **Bad-day replay:** batch-run every qualifying flight into one airport on one bad day and show the summary stats (§8).
9. **Approve button:** human sign-off, which closes the hash chain.

---

## 8. Honest evaluation

### 8.1 Test set

- **N = 30** qualifying rows by default (free-tier rate limits), **N = 100** if quota allows, split across teammates' API keys. Stratified across delay type (weather vs. late aircraft) and at least 5 airports. Held out from any prompt tuning.
- Plus **5 hand-picked rows** used during development, reported separately.
- **Status quo cost (computed, not assumed):** count of qualifying 2015 flights and total delay minutes, from the dataset.

### 8.2 Baselines

| ID | Baseline |
|---|---|
| B0 | Naive FCFS: next free runway slot + first free compatible gate, flight plan as filed |
| B1 | Deterministic optimiser (= the fallback) |
| B2 | Single-agent ablation: one LLM sees everything. **Evaluation only**, to quantify what multi-agent adds. Never used in the product. |
| B3 | Model ablation: all agents on Gemini 3.6 Flash or Gemma 4 (if quota allows) |

### 8.3 Metrics

| Metric | Why it matters |
|---|---|
| Consensus rate; % by R2; % by R3 | Core challenge goal |
| Fallback / escalate rate | How often the AI can't agree |
| **Unsafe proposals blocked** (count of agent proposals or acceptances that failed a hard constraint) | Proves the checker is necessary |
| **Unsafe plans executed** | Must be **0** |
| Schema failure / retry rate | Reliability of structured messaging |
| Plan cost J vs. B0 and B1 (regret) | Plan quality |
| Bank delay added, misconnected pax, overtime vs. B0 | Impact in operational terms |
| Latency p50 / p95 per resolution; tokens and cost per resolution | Practicality |

**We expect** LLM consensus to sometimes score worse on J than the optimiser B1, and we will report that openly. ACCORD's value is negotiated, explained, cross-domain buy-in with the optimiser as a safety net. It is not a claim to beat a solver at arithmetic.

### 8.4 Failure cases to show (at least one live)

1. **Deadlock:** Pilot refuses any option with misconnects above X, Ground refuses overtime, R3 ballot fails → fallback, with the log showing exactly why.
2. **Unsafe agreement caught:** agents converge on an option that breaks H3 by 2 minutes of fuel → the checker vetoes it.
3. **Hallucinated reference:** an agent cites a non-existent gate → the enum validation rejects it, and it counts as REJECT.

---

## 9. Architecture and repo

```
accord/
├── LICENSE                     # MIT
├── README.md                   # setup, limitations, synthetic-data disclosure
├── config.yaml                 # models per agent, weights, MAX_ROUNDS, thresholds
├── data/prep.py                # Polars filter → qualifying.parquet
├── core/
│   ├── scenario.py             # row + arrival bank + connections + seeded synthetic
│   ├── options.py              # grid → Pareto-pruned candidates
│   ├── metrics.py              # per-option metric computation
│   ├── constraints.py          # H1–H7 checker
│   ├── fallback.py             # weighted lexicographic optimiser
│   └── log.py                  # hash-chained JSONL
├── agents/
│   ├── schema.py               # Pydantic models + dynamic enums
│   ├── prompts/agent.md.j2     # the ONE merged template (blocks A–E)
│   ├── client.py               # async Gemini calls, JSON schema output, 429 back-off, retries
│   └── coordinator.py          # state machine R1→R2→R3→consensus/fallback
├── api/server.py               # FastAPI: /scenarios, /run (SSE stream), /chaos, /approve
├── web/                        # Vite + React + Tailwind console, SVG Gantt, Leaflet route map
├── eval/run_eval.py            # batch N=30 (100 if quota allows), baselines, ablations → results.json
└── tests/                      # checker + fallback unit tests, golden scenarios
```

**Stack:** Python 3.11, Polars, Pydantic v2, FastAPI + Server-Sent Events, `google-genai` SDK (async, `asyncio.gather` for the three parallel agent calls), Vite + React + Tailwind, Leaflet (dark free tile layer, or a plain US outline if tiles are unavailable) for the map.
**Map data:** the `/scenarios/{id}` endpoint returns each flight in the window with origin/destination coordinates joined from `airports.csv`, scheduled times and a role tag (`disrupted`, `bank`, `connection`).
**Fallback UI:** if the React build stalls, a Streamlit console reuses the same `core/` and `agents/` packages.

---

## 10. Five-hour build plan (AI-driven)

The build assumes AI coding agents do most of the implementation, with the team acting as architects, reviewers and testers. The key is **contract-first parallelism**: define the schemas and interfaces in the first 30 minutes, then run parallel AI coding sessions (separate git worktrees) against those contracts.

| Time | Workstream 1: Core (deterministic) | Workstream 2: Agents | Workstream 3: Console | Humans |
|---|---|---|---|---|
| **0:00–0:30** | Repo, LICENSE, `config.yaml`, `data/prep.py` run. **Freeze `schema.py` and the `Scenario`/`Option`/`Metrics` dataclasses.** | — | — | Download data, set API keys, pick 5 dev rows |
| **0:30–1:30** | `scenario.py`, `options.py`, `metrics.py`, `constraints.py`, `fallback.py` + unit tests. **Milestone: CLI prints options + checker grid + fallback plan for any row.** | Template blocks A–E, role charters, `client.py` with tool forcing + caching | Console layout, mock SSE stream from a fixture JSON | Review checker rules for realism |
| **1:30–2:30** | `log.py` hash chain; chaos event mutators | `coordinator.py` state machine. **Milestone: full R1–R3 negotiation on one row via CLI, with log.** | Negotiation room, constraint wall, Gantt components on mock data | Read transcripts, tune charters |
| **2:30–3:15** | **Integration:** FastAPI SSE wired to the real coordinator; console on live data | ← | ← | Smoke-test 10 random rows |
| **3:15–4:00** | `eval/run_eval.py` running N=30 + baselines **in the background**, split across API keys | Kill switch, narrator, grounding check (stretch) | **Traffic map** (route arcs, moving markers, chaos highlight), chaos button, approve flow, eval results page | Select failure cases |
| **4:00–4:30** | Eval results into the UI + README limitations | Fix the top 1–2 issues found by eval | Polish, loading states, demo fixtures cached | Slides (4 max) |
| **4:30–5:00** | **Feature freeze.** Tag release. | — | — | Rehearse the 3-min demo ×2, **submit early** |

**Cut order if behind schedule** (never cut the items in bold):
1. Grounding check
2. Narrator
3. Map animation (keep static arcs)
4. Bad-day replay
5. React → Streamlit (map via `pydeck`)
6. N=30 → N=15
7. Model ablation

**Never cut:** separate agent calls, the checker, the fallback, the turn limit, the hash-chained log, and one shown failure case.

**Demo insurance:** cache the full event stream for 2 hero scenarios. If the venue Wi-Fi or the API fails, replay the recorded stream and say so.

---

## 11. Three-minute pitch

| Time | Content |
|---|---|
| 0:00–0:25 | **Problem:** one real delayed flight from the dataset; today's phone-call chain; computed status-quo delay minutes |
| 0:25–1:40 | **Live:** load the scenario → the map shows the late flight and the traffic converging on the airport → three agents negotiate → a red veto on an unsafe counter → consensus in R2 → hit Chaos (taxiway blocked) → re-negotiation → approve |
| 1:40–2:20 | **Evidence:** consensus rate, % by R2, unsafe proposals blocked vs. 0 executed, cost vs. baselines |
| 2:20–2:45 | **Failure:** deadlock → fallback; flip the kill switch; show the log explaining why |
| 2:45–3:00 | **Limits:** synthetic fields, simplified separation and fuel rules, human approves every plan |

---

## 12. Rubric alignment

| Criterion (weight) | Evidence ACCORD provides |
|---|---|
| Problem realism (20%) | Named user (AOC duty manager), real DOT disruption rows, real arrival banks and connections, computed status-quo cost |
| Technical soundness (25%) | End-to-end live build; LLMs negotiate and explain, code computes and enforces; handles any qualifying row plus chaos events, not a scripted demo |
| Honest evaluation (20%) | N=30–100 held-out set, 4 baselines/ablations, unsafe-blocked metric, regret vs. optimiser reported even when unflattering, live failure case |
| Trust & traceability (20%) | Hash-chained log citing source row, constraint IDs and metric references; synthetic data tagged; ESCALATE when no safe plan exists; human approval |
| Impact (10%) | Before/after vs. FCFS baseline in delay minutes, misconnects and overtime, all labelled as simulation results; resolution latency in seconds |
| Time discipline (5%) | Freeze at 4:30, early submission, rehearsed 3-minute pitch |

---

## 13. Known limitations (stated up front)

- Fuel, gates, wake categories, crew and turbulence are **synthetic**. Results show coordination behaviour, not real-world operational accuracy.
- The separation and fuel rules are simplified illustrations, not certified procedures.
- 2015 data has no aircraft types, gate assignments or ATC flow programmes.
- Map positions are interpolated from schedule times, not real tracks; the 2015 data has no radar or holding data.
- Runs on free-tier models, so batch evaluation size is limited by rate limits.
- A single runway is modelled per airport. There is no multi-airport network effect beyond the connections at the destination.
- LLM behaviour is stochastic. We report variance across repeated runs of the dev scenarios.
