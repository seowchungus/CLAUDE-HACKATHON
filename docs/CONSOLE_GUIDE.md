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
| Recorded hero 1 (offline) | http://127.0.0.1:8000/?replay=dl2463 |
| Recorded hero 2 (offline) | http://127.0.0.1:8000/?replay=oo6476 |
| Scripted deadlock | http://127.0.0.1:8000/?autorun=1&mode=deadlock |
| Evaluation results | http://127.0.0.1:8000/?eval=1 |

---

## 2. Run a scenario in 4 steps

1. **Pick a flight.** Use the dropdown at the top. The two demo flights are pinned as **★ hero**. For any other flight:
   - type a `flights.csv` row number (0 – 358773) or a scenario id into **Row # or scenario id**, then press **Load**;
   - or click **🎲 Random row**.
2. **Click ▶ Run.** The three agents start negotiating. Watch the round tracker: **R1 → R2 → R3**.
3. **Read the result** in the **Decision** panel:

   | Result | Meaning |
   |---|---|
   | **CONSENSUS** | The agents agreed. |
   | **FALLBACK** | They didn't; the optimiser chose. |
   | **ESCALATE** | No safe plan exists; a human must choose. |

4. **Sign off.** Enter your name and click **Approve**, or choose another option under *override with…* and click **Override**. The panel shows **✓ Signed**.

A run takes 30–60 s on the free tier (calls are limited to 12 per minute). One agent answer takes 2–8 s.

---

## 3. What's on the screen

### Header (top)

| Item | What it does |
|---|---|
| **Console / Eval** | Switches view |
| Dropdown, **Row #**, **🎲 Random row** | Choose a flight |
| **▶ Run** | Start the negotiation |
| **⚡ Chaos** | Inject a new disruption (§4) |
| **☠ Kill the LLM** | Simulate the AI being down |
| **LLM OFF · restore** | Switch the AI back on |
| **Demo scenarios…** | Failure demos and replays (§5) |
| **Log ✓** | Open the consensus log |
| Budget meter | Gemini calls used today |

Budget meter colours: **amber** above 80 %, **red** at the cap. At the cap, Run uses the fallback only.

### Scenario bar

Shows the real delayed flight: airline, route, date, delay type, delay minutes, and *flights.csv row N*.

Every value has a tag:

| Tag | Meaning |
|---|---|
| **REAL** | From the 2015 US DOT data |
| **DERIVED** | Calculated from real data |
| **SYNTHETIC** | Generated; the public data doesn't have it |

Synthetic fields: fuel, gates, crew, wake category, connecting passenger counts, turbulence. They're seeded, so the same flight always gives the same values.

### Traffic map

| You see | Meaning |
|---|---|
| Highlighted arc | The delayed flight |
| Other arcs | Flights competing for the same runway |
| Dashed lines | Connections at risk |
| Amber ring | A chaos event is active |

Aircraft positions are *estimated* from schedule times; the data has no radar tracks.

### Negotiation room

Three columns: **ATC**, **PILOT**, **GROUND**. Each card is **one separate AI call** that sees only that role's own data.

| On a card | Meaning |
|---|---|
| **PROPOSE / COUNTER / ACCEPT / REJECT** | The agent's move |
| Ranking | Options it prefers, best first |
| Acceptable | Options it can live with |
| Red lines | Rules it won't break |
| Rationale | Its reason, citing metrics |
| **UNGROUNDED** | Quoted a number that doesn't match its cited metric |
| Red shake | Counter rejected by the checker |
| Veto banner | Checker overruled an unsafe agreement |

**UNGROUNDED** is shown, not trusted: code computes every number.

**How the rounds work:**
- One round = each agent sends one message.
- **R1:** each agent proposes.
- **R2:** each agent responds to the others.
- **R3:** final vote, no new proposals.
- All three accept → consensus. No agreement after R3 → the fallback decides, and the log says why.

### Constraint wall

Each **row** is an option (`opt_1`, `opt_2`, …; `opt_c1` = an agent's counter-proposal). Each **column** is a hard rule:

| Rule | Checks | Owner |
|---|---|---|
| **H1** Wake | Gap behind the previous arrival | ATC |
| **H2** Capacity | Arrivals this hour within limit | ATC |
| **H3** Fuel | ≥ 30 min fuel at landing | Pilot |
| **H4** Gate | Free, right size, ≥ 20 min notice | Ground |
| **H5** Crew | Within the 13 h duty limit | Ground / Pilot |
| **H6** Taxiway | Route to the gate is open | ATC / Ground |
| **H7** Turbulence | No severe turbulence | Pilot |

| Marker | Meaning |
|---|---|
| Green / red cell | Passes / fails (hover for the reason) |
| **WB** / **ours** in a header | Limit from the workbook / our rule |
| Outlined row | Current tentative plan |
| **PLAN** | Final choice |
| **B1** | The optimiser's pick |
| **B0** | First-come-first-served (often breaks a rule) |

The **Challenge limits** panel beside the wall shows the airport's workbook limits and, in amber, our **Deviations from the workbook**.

### Runway & gates (timeline)

| Lane | Shows |
|---|---|
| Runway | Landing slots; the plan's slot |
| Gates | When each gate is busy; the plan's gate window |
| Red glow | A conflict |

### Decision panel

| Shows | Example |
|---|---|
| New arrival time | 14:49 (+10 min) |
| Gate | B3 |
| Flight-plan change | speed reduction |
| Source | CONSENSUS / FALLBACK (with reason) |
| Key metrics | delay, fuel, missed connections, overtime |

### Consensus log (Log ✓)

- Every event in order: scenario, options, agent messages, checks, decision, sign-off.
- Each entry has a timestamp, the source flight, the rules applied, and a hash linked to the previous entry.
- **Chain verified ✓** = nothing was edited afterwards.
- **Download .jsonl** saves it.

---

## 4. Chaos: inject a disruption

Click **⚡ Chaos**, pick a type, then click **Inject & re-negotiate**.

| Type | Effect |
|---|---|
| **RUNWAY_CLOSURE** | Runway capacity halved |
| **TAXIWAY_BLOCK** | Gates behind it unreachable (H6 fails) |
| **GATE_FAILURE** | One gate out of service |
| **WEATHER_CELL** | More turbulence and delay |

A **new run** starts. The old one is marked **SUPERSEDED**, the map ring turns amber, and the agents negotiate again.

---

## 5. Failure demos and backups

Open **Demo scenarios…**:

| Option | What happens | Badge |
|---|---|---|
| **Deadlock → fallback** | Agents never agree; optimiser decides | SCRIPTED |
| **Unsafe agreement → veto** | Checker blocks an unsafe agreement | SCRIPTED |
| **Hallucinated citation → REJECT** | Agent cites a gate that doesn't exist | SCRIPTED |
| **Recorded replays** | Real recorded hero runs (works offline) | REPLAY |

- Sign-off is disabled on replays.
- **☠ Kill the LLM**: the next run skips the AI; the optimiser plans instantly (0 AI calls), still checked against H1–H7.

---

## 6. Evaluation page (Eval tab)

Results on a frozen held-out set of 30 real flights, against two baselines: **B1** (optimiser) and **B0** (first-come-first-served).

| Badge | Meaning |
|---|---|
| **MEASURED** | Live AI run |
| **SCRIPTED AGENTS (mock)** | Not an AI result |
| **Deterministic baselines only** | No AI run |

**Read with this note:** in the live run, 12 of 30 flights hit a client bug (since fixed) before any agent replied, and fell back to the optimiser.

| Live result | Value |
|---|---|
| Flights that negotiated | 18 |
| Reached consensus in round 2 | 18 of 18 |
| Unsafe plans executed (all 30) | 0 |

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| Page won't load | Start the server (§1) |
| **FALLBACK (LLM_ERROR)** | Gemini unreachable; plan is still safe. Retry or use a replay. |
| *Budget exhausted* on Run | Use replays, or wait for the 15:00 (Singapore) reset |
| **LLM OFF** showing | Click **LLM OFF · restore** |
| Log badge ✗ | Log was modified; badge names the broken entry |

---

## 8. Limits

- Fuel, gates, crew, wake and turbulence are **synthetic** and tagged.
- Rules are simplified, **not ICAO-certified**.
- One runway per airport.
- A human approves every plan.
