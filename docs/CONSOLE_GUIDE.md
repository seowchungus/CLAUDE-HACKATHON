# ACCORD Console: User Guide

The console is where a duty manager watches three AI agents (Air Traffic Control, Pilot, Ground Ops) negotiate a fix for a delayed flight, checks that the plan is safe, and signs it off.

---

## 1. Start it

```bash
cd ACCORD
. .venv/bin/activate
uvicorn api.server:app --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000** in Chrome or Safari.

- Needs `data/qualifying.parquet` (run `python data/prep.py` once) and a Gemini key in `.env`.
- **No key or no internet?** Start with `MOCK=1 uvicorn api.server:app --host 127.0.0.1 --port 8000`. Every run then uses scripted agents and shows a **SCRIPTED** badge.
- Each live run uses about 6 Gemini calls. The budget meter in the header shows how many are left today.

### Quick links
| Purpose | Link |
|---|---|
| Console | http://127.0.0.1:8000 |
| Hero flight, auto-start | http://127.0.0.1:8000/?scenario=2015-12-30_DL2463_ICT-ATL&autorun=1 |
| Recorded hero (no network needed) | http://127.0.0.1:8000/?replay=dl2463 · http://127.0.0.1:8000/?replay=oo6476 |
| Scripted deadlock | http://127.0.0.1:8000/?autorun=1&mode=deadlock |
| Evaluation results | http://127.0.0.1:8000/?eval=1 |

---

## 2. Run a scenario in 4 steps

1. **Pick a flight.** Use the dropdown at the top. The two demo flights are pinned as **★ hero**. To use any other flight:
   - type a row number of `flights.csv` (0 – 358773) or a scenario id into **Row # or scenario id**, then press **Load**;
   - or click **🎲 Random row**.
2. **Click ▶ Run.** The three agents start negotiating. Watch the round tracker: **R1 → R2 → R3**.
3. **Read the result** in the **Decision** panel: **CONSENSUS** (the agents agreed), **FALLBACK** (they didn't; the optimiser chose), or **ESCALATE** (no safe plan exists; a human must choose).
4. **Sign off.** Enter your name and click **Approve**, or choose another option under *override with…* and click **Override**. The panel shows **✓ Signed** and the log is closed with your signature.

A run takes 30–60 s on the free tier, because calls are limited to 12 per minute. One agent answer takes 2–8 s.

---

## 3. What's on the screen

### Header (top)
| Item | What it means |
|---|---|
| **Console / Eval** | Switch between the live console and the evaluation results. |
| Scenario dropdown, **Row #**, **🎲 Random row**, **▶ Run** | Choose and start a flight (see §2). |
| **⚡ Chaos** | Inject a new disruption mid-run (see §4). |
| **☠ Kill the LLM** | Simulates the AI being down. It turns into **LLM OFF · restore**; click again to switch the AI back on. |
| **Demo scenarios…** | Scripted failure cases and recorded replays (see §5). |
| **Log ✓** | Opens the consensus log; ✓ means the hash chain is intact. |
| Budget meter (e.g. *Flash-Lite 223/480 today*) | Gemini calls used today. Amber above 80 %, red at the cap. At the cap, Run uses the fallback only. |

### Scenario bar
The real delayed flight: airline and number, route, date, delay type (**WEATHER** or **LATE_AIRCRAFT**), delay minutes, and *flights.csv row N*.
Every value has a tag:
- **REAL**: straight from the 2015 US DOT data
- **DERIVED**: calculated from real data
- **SYNTHETIC**: generated, because the public data doesn't have it (fuel, gates, crew, wake category, connecting passenger counts, turbulence). Generated values are seeded, so the same flight always gives the same values.

### Traffic map
- **Highlighted arc**: the delayed flight.
- **Other arcs**: the arrival bank, the flights competing for the same runway.
- **Dashed lines**: connecting flights whose passengers may miss their connection.
- **Amber ring** on the airport: a chaos event is active.
- Aircraft positions are *estimated* from schedule times (the data has no radar tracks).

### Negotiation room
Three columns: **ATC**, **PILOT** and **GROUND**. Each card is **one separate AI call** that sees only that role's own data.
| On a card | Meaning |
|---|---|
| **PROPOSE / COUNTER / ACCEPT / REJECT** | The agent's move this round. |
| Ranking, acceptable list | The options it prefers and the ones it can live with. |
| Red lines | Rules it won't break, e.g. `H3_fuel_reserve`. |
| Rationale | Its reason, citing metrics as `opt_3.misconnected_pax`. |
| **UNGROUNDED** | The agent quoted a number that doesn't match the metric it cited. It's shown, not trusted: code computes every number. |
| Red shake | A counter-proposal that broke a hard rule was rejected by the checker. |
| Veto banner | The agents agreed on an option that breaks a rule, and the checker overruled them. |

**Rules of the negotiation.** One round = each agent sends one message. Round 1: each agent proposes. Round 2: each agent responds to the others. Round 3: a final vote, with no new proposals allowed. If all three accept, that's consensus. After 3 rounds without agreement, the fallback decides and the log says why.

### Constraint wall
A grid: each row is an option (`opt_1`, `opt_2`, … and `opt_c1` for agent counter-proposals); each column is a hard rule.

| Rule | Checks | Owner |
|---|---|---|
| **H1** wake separation | enough time behind the previous arrival | ATC |
| **H2** runway capacity | arrivals this hour ≤ reduced capacity | ATC |
| **H3** fuel reserve | at least 30 min of fuel left at landing | Pilot |
| **H4** gate validity | gate free, right size, gate change announced ≥ 20 min ahead | Ground |
| **H5** crew duty | flight crew within the 13 h duty limit | Ground/Pilot |
| **H6** taxiway | the route to the gate isn't blocked | ATC/Ground |
| **H7** turbulence | not into severe turbulence | Pilot |

- **Green** means it passes, **red** means it fails. **Hover a cell** for the exact reason.
- **WB** in a header means the limit comes from the organisers' workbook; **ours** means it's our rule.
- The **outlined row** is the current tentative plan; **PLAN** marks the final choice.
- **B1** = what the deterministic optimiser would pick. **B0** = naive first-come-first-served (greyed out; often breaks a rule).
- **Challenge limits** panel beside the wall: the airport's workbook row, the wake table, fuel and crew rules, and, in amber, **Deviations from the workbook**.

### Runway & gates (timeline)
- **Runway lane**: landing slots for the arrival bank and the plan's slot.
- **Gate rows**: when each gate is busy, the plan's gate window, and any gate change with its notice time.
- **Red glow** marks a conflict (overlap or too little separation).

### Decision panel
The final plan: new arrival time, gate, flight-plan change (as filed, speed reduction, holding, weather reroute), and its key metrics (delay added, fuel at landing in min and kg, missed connections, ramp overtime). It says where the plan came from, **CONSENSUS** or **FALLBACK** (with the reason), or shows **ESCALATE** if no option is safe.

### Consensus log (Log ✓)
Every event in order: scenario loaded, options, each agent message, every check, the decision, and your sign-off. Each entry has a timestamp, its source flight, the rules applied, and a hash linked to the previous entry. **Chain verified ✓** means nothing was edited afterwards. **Download .jsonl** saves it.

---

## 4. Chaos: inject a disruption

Click **⚡ Chaos**, pick a type, then click **Inject & re-negotiate**:
| Type | Effect |
|---|---|
| **RUNWAY_CLOSURE** | runway capacity halved |
| **TAXIWAY_BLOCK** | pick a taxiway; gates behind it become unreachable (H6 fails) |
| **GATE_FAILURE** | pick a gate; it goes out of service |
| **WEATHER_CELL** | more turbulence and more delay |

A **new run** starts from the updated situation. The old run is marked **SUPERSEDED**, the map ring turns amber, and the agents negotiate again.

## 5. Failure demos and backups

**Demo scenarios…** menu:
- **Scripted failures (mock agents)**, shown with a **SCRIPTED** badge:
  - **Deadlock → fallback**: the agents never agree, and the optimiser decides after round 3.
  - **Unsafe agreement → veto**: the agents agree on an unsafe option, and the checker blocks it.
  - **Hallucinated citation → REJECT**: an agent cites an option or gate that doesn't exist, and it's rejected.
- **Recorded replays**: real recorded runs of the hero flights, shown with a **REPLAY** badge. Use these if the network or Gemini fails. Sign-off is disabled on replays.

**☠ Kill the LLM**: the next run skips the AI entirely and the optimiser plans instantly (0 AI calls), still checked against H1–H7.

---

## 6. Evaluation page (Eval tab)

Results on a frozen held-out set of 30 real flights, compared with the two baselines (**B1** optimiser, **B0** first-come-first-served). The headline tiles are consensus rate, unsafe plans executed (must be 0), schema failures, latency, and tokens.
Badges: **MEASURED** = live run. **SCRIPTED AGENTS (mock)** = not an AI result. **Deterministic baselines only** = no AI run.

Read with the README note: in the live run, 12 of 30 flights hit a client bug (since fixed) before any agent replied, and fell back to the optimiser. On the **18 flights where the agents negotiated, 18 reached consensus in round 2**, and no unsafe plan was executed on any of the 30.

---

## 7. Troubleshooting
| Symptom | Fix |
|---|---|
| Page won't load | Start the server (§1); check nothing else uses port 8000. |
| Run ends in **FALLBACK (LLM_ERROR)** | Gemini unreachable or rate-limited. The plan is still safe. Retry, or use a replay. |
| Run button says *fallback only: LLM budget exhausted* | Today's call cap is reached. Use replays, or wait for the reset (midnight Pacific = 15:00 Singapore). |
| **LLM OFF** showing | Click **LLM OFF · restore**. |
| Log badge shows ✗ | The log file was modified; the badge names the first broken entry. |

## 8. Limits to keep in mind
Fuel, gates, crew, wake and turbulence are synthetic and tagged. The rules are simplified, not ICAO-certified. One runway is modelled per airport. A human approves every plan.
