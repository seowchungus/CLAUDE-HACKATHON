# ACCORD pitch draft (3 min) — MANAGER, 14:15
Every number below is measured from the repo. ⏳ = filled from W1-08b (`eval/results.json`, `llm: "live"`) at ~14:50. Never round up, never extrapolate.

## 0:00–0:25 Problem
- "One real flight: **DL2463 Wichita → Atlanta, 30 Dec 2015**, delayed on the worst day for Atlanta in the data." (hero; show the scenario bar with REAL/SYNTHETIC tags)
- "Today ATC, the crew and the ramp fix this by phone, one after another."
- Status quo, computed by `data/prep.py`: "**Across the 358,774 qualifying delayed flights in the provided 2015 DOT data**, that's **2.9 million minutes** of weather delay and **21.6 million minutes** of late-aircraft delay." (Never say "all 2015 flights".)

## 0:25–1:40 Live
1. Load DL2463 → map: the late flight, the arrival bank converging on ATL, dashed connections at risk.
2. Three agents negotiate, **three separate Gemini calls per round**, each with only its own private data. Round tracker R1 → R2.
3. Constraint wall: options × H1–H7, green/red. "Agents rank and argue. **Code** computes every number and checks every rule."
4. Consensus in R2 (all 3 live smoke runs: UA1575, DL2463, OO6476 reached consensus in round 2, feasible, ~4–8 s per call).
5. **Chaos: TAXIWAY_BLOCK** → amber ring, a new child run, and a tempting option behind the blocked taxiway goes red on H6 → re-negotiation.
6. Approve → "Signed: <hash>", chain verified ✓.

## 1:40–2:20 Evidence (frozen held-out set, sha256 4474f237…, committed before any run)
- "On **N = ⏳** held-out flights (6 hubs, half weather, half late aircraft): consensus **⏳%**, **⏳%** by round 2, fallback **⏳%**."
- "Unsafe proposals blocked: **⏳**. Unsafe plans executed: **⏳ (must be 0)**."
  - If blocked = 0: "On live runs the agents never proposed a rule-breaking option, so the checker had nothing to block. We show it catching one with **scripted agents** (labelled SCRIPTED); we did not see a live veto." (Human decision 14:05: do not claim a live veto.)
- Plan quality vs the optimiser: "mean cost J: ACCORD **⏳**, optimiser **71.36**, FCFS **68.74**." Say why FCFS looks cheapest: "**FCFS breaks a hard rule on 40% of these flights.** It's cheap because it's illegal." Report regret vs B1 (⏳) even if ACCORD is worse: "We don't claim to beat a solver at arithmetic; we add negotiated, explained buy-in, with the solver as the safety net."
- Bad day, deterministic only (ATL, 30 Dec 2015, 438 arrivals): "First-come-first-served breaks a hard rule on **161 of 438** flights. On the 424 flights where the optimiser found a legal plan, it cuts knock-on bank delay from **5,443 to 2,973 minutes**, at the cost of more misconnects (28,222 → 29,241) and ramp overtime (1,305 → 2,170 min). 14 flights have no safe automated plan → ESCALATE to the human."

## 2:20–2:45 Failure
- Demo menu → **deadlock** (SCRIPTED): ballot fails in R3 → deterministic fallback, the log says why.
- **Kill the LLM**: next run falls back instantly, 0 LLM calls, plan still feasible.

## 2:45–3:00 Limits (say them, they're on the slide)
- Fuel, gates, wake, crew, turbulence are **synthetic** and labelled; rules simplified, not ICAO/certified.
- Limits follow the organisers' workbook; **our deviations are listed in the console** (capacity = 50% of ops, gate wait ≤ 30 min, H7 threshold, crew-duty floor…).
- One free-tier project: 500 calls/day; one model (Gemini 3.5 Flash Lite) for all agents, for parity.
- A human approves every plan.

## Slides (max 4)
1. Problem + status-quo numbers. 2. Architecture: 3 agents → coordinator (≤3 rounds) → checker H1–H7 → fallback → human; hash-chained log. 3. Evaluation table (⏳) + bad day. 4. Limits + deviations.

## Do not say
- "all 2015 flights" · "beats the optimiser" (unless measured) · "a live veto was shown" · "certified / ICAO" · any number not in `eval/results.json` or `data/status_quo.json`.
