# ACCORD

**Autonomous Cross-domain Coordination for Operational Resolution of Disruptions.**
Autonomous SG 2026 · AI & Aerospace Track · Airbus Challenge #2.

Three AI agents (ATC, Pilot, Ground Ops), each in its own LLM call with its own private data, negotiate a revised arrival time, gate and flight-plan adjustment for a disrupted flight in at most 3 rounds. A deterministic checker (H1–H7) enforces hard constraints, and a deterministic optimiser takes over if the agents don't agree or the LLM is off. A duty manager approves the result. Every step goes into a hash-chained log.

Spec: [ACCORD_proposal.md](ACCORD_proposal.md) · Interfaces: [docs/CONTRACTS.md](docs/CONTRACTS.md) · **Console user guide: [docs/CONSOLE_GUIDE.md](docs/CONSOLE_GUIDE.md)**

## Setup
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env            # add GEMINI_API_KEY (free tier)
# put flights.csv, airlines.csv, airports.csv (US DOT 2015) in data/raw/
python data/prep.py             # -> data/qualifying.parquet
python -m core.cli --dev 0      # options + checker grid + fallback, no LLM
uvicorn api.server:app --port 8000
cd web && npm install && npm run dev
```
Offline demo with no data or key: `MOCK=1 uvicorn api.server:app --port 8000`.

## Evaluation (measured; `eval/results.json`)
Held-out set frozen before any run: `eval/eval_set.json` (N=30, 6 hubs, 15 weather / 15 late-aircraft, seed 42, sha256 `4474f237…`). Dev rows and hero scenarios are excluded.

Live run: Gemini 3.5 Flash Lite for all three agents, key 1, 144 calls (`eval/results.json`, commit 655213e).

**What happened:** 12 of the 30 flights never negotiated. A client bug ("Event loop is closed", fixed in cac78e9 during the run) failed every agent call in round 1, and the deterministic fallback produced their plans (still feasible). A partial re-run with the fixed client was stopped after 4 of the 12 (all 4 reached consensus in round 2; logs in `runs/`, **not merged**), so the agent results below cover the **18 flights that negotiated in the first pass**.

| On the 18 negotiated flights | ACCORD (live LLM) | B1 optimiser | B0 FCFS |
|---|---|---|---|
| Consensus | **18/18, all in round 2** | n/a | n/a |
| Mean cost J (lower is better) | 78.66 | 77.66 | 73.41 |
| Plans breaking a hard rule | **0** | 0 | 7 of 18 |
| Same plan as the optimiser | 5 of 18 | | |
| Unsafe proposals blocked by the checker | 0 (agents never proposed one) | | |
| Schema failures | 0% | | |
| Agent messages with a number that doesn't match a cited metric ("ungrounded") | 44 of 103 (43%) | | |
| Time per resolution (median) | 52 s, mostly the free-tier 12 requests/min limiter; one call takes ~2–8 s | | |
| Tokens per resolution (mean) | 18,655 | | |

All 30 flights: 0 unsafe plans executed. Mean regret vs the optimiser is +1.0 J per flight. The agents trade a little cost for a negotiated, explained plan; they don't beat the solver. B0 has the lowest mean J because it breaks a hard rule on 40% of the 30 rows (7 of these 18); its cost isn't comparable to a legal plan's. Ungrounded numbers never reach the plan, since code computes every metric and the checker decides legality, but they show why LLM text can't be trusted with numbers.

**Bad day (deterministic baselines only, no LLM):** ATL, 2015-12-30, 438 qualifying arrivals (`python -m eval.bad_day`). FCFS breaks a hard rule on 161. On the 424 flights where the optimiser found a legal plan, it cuts knock-on bank delay from 5,443 to 2,973 min, with more misconnected passengers (28,222 → 29,241) and ramp overtime (1,305 → 2,170 min). 14 flights have no safe automated plan and escalate to the human.

**Status quo:** across the 358,774 qualifying delayed flights in the provided 2015 DOT data, 2,895,086 min of weather delay and 21,558,009 min of late-aircraft delay (`data/status_quo.json`).

**Live checks (INT-01):** three live runs (UA1575 DEN-ORD, DL2463 ICT-ATL, OO6476 AUS-SFO) reached consensus in round 2 on feasible plans, three separate calls per round, hash chains verified. None of them produced a veto; checker vetoes are demonstrated with **scripted** agents (labelled SCRIPTED in the console).

## Known limitations
- Fuel, gates, wake categories, crew and turbulence are **synthetic** and tagged as such in the UI and the log. Results show coordination behaviour, not operational accuracy.
- Separation and fuel rules are simplified illustrations, **not ICAO or certified values**.
- 2015 DOT data has no aircraft types, gate assignments, ATC flow programmes, radar tracks or holding data. Map positions are interpolated from schedule times.
- One runway modelled per airport; no network effect beyond connections at the destination.
- Gate wait is our rule, not the workbook's: an aircraft may wait up to 30 min on the ramp for its gate to free up; longer and the gate is invalid (H4).
- Operational limits (capacity, wake, fuel, crew, gates) follow the organisers' workbook `challenge2_operational_constraints.xlsx`, whose values are, in the organisers' words, synthetic planning limits scaled from traffic; our deviations from it are listed in `config.yaml` (`workbook_deviations`) and in the console.
- The provided flights file contains delayed flights only (as issued by the organisers; October 2015 is not included), so arrival banks and connections show delayed traffic only.
- Free-tier models (Gemini 3.5 Flash Lite, 500 requests/day) limit the evaluation size; a hard call budget is enforced in code. LLM behaviour is stochastic.
- A human approves every plan. ACCORD does not replace expert judgement.

## License
MIT
