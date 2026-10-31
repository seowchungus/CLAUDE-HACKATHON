# ACCORD

**Autonomous Cross-domain Coordination for Operational Resolution of Disruptions.**
Autonomous SG 2026 · AI & Aerospace Track · Airbus Challenge #2.

Three AI agents (ATC, Pilot, Ground Ops), each in its own LLM call with its own private data, negotiate a revised arrival time, gate and flight-plan adjustment for a disrupted flight in at most 3 rounds. A deterministic checker (H1–H7) enforces hard constraints, and a deterministic optimiser takes over if the agents don't agree or the LLM is off. A duty manager approves the result. Every step goes into a hash-chained log.

Spec: [ACCORD_proposal.md](ACCORD_proposal.md) · Interfaces: [docs/CONTRACTS.md](docs/CONTRACTS.md)

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

## Status
Under construction (hackathon build). Evaluation results and limitations are filled in from measured runs.

## Known limitations
- Fuel, gates, wake categories, crew and turbulence are **synthetic** and tagged as such in the UI and the log. Results show coordination behaviour, not operational accuracy.
- Separation and fuel rules are simplified illustrations, **not ICAO or certified values**.
- 2015 DOT data has no aircraft types, gate assignments, ATC flow programmes, radar tracks or holding data. Map positions are interpolated from schedule times.
- One runway modelled per airport; no network effect beyond connections at the destination.
- Operational limits (capacity, wake, fuel, crew, gates) follow the organisers' workbook `challenge2_operational_constraints.xlsx`; our deviations from it are listed in `config.yaml` (`workbook_deviations`) and in the console.
- The provided flights file contains delayed flights only (as issued by the organisers; October 2015 is not included), so arrival banks and connections show delayed traffic only.
- Free-tier models (Gemini 3.5 Flash Lite, 500 requests/day) limit the evaluation size; a hard call budget is enforced in code. LLM behaviour is stochastic.
- A human approves every plan. ACCORD does not replace expert judgement.

## License
MIT
