# Team protocol (all chats read this)

Clock: **T0 = 11:09 (+08), Sat 31 Oct 2026.** Hard deadline 16:09. **Feature freeze 15:39.** Run `date` at the start of every turn.

## Who owns what (only edit your own paths)
| ID | Role | Owned paths |
|---|---|---|
| MANAGER | Plan, contracts, delegation, tracking | `.team/` (except reviews/status), `docs/`, `config.yaml`, `requirements.txt`, `README.md`, `LICENSE`, `.gitignore`, `.env.example` |
| W1 | Core (deterministic) | `data/`, `core/`, `eval/`, `tests/` |
| W2 | Agents (LLM) | `agents/` (tests go in `agents/tests/`) |
| W3 | Console | `api/`, `web/` |
| REVIEWER | Reviews | `.team/reviews/` |

Everyone may append to their own `.team/status/<ID>.md`. Nobody edits another person's files. If you need a change elsewhere, write `BLOCKED <task>: need X in <path>` in your status file and continue with something else; MANAGER creates the task.

## Source of truth
1. `ACCORD_proposal.md` (product spec)
2. `docs/CONTRACTS.md` (FROZEN types, events, endpoints, log format). Build against it exactly. Do not rename fields. If something is missing or wrong, report it as BLOCKED; don't improvise a different shape.
3. `config.yaml` (models, thresholds, weights). Read it, never hardcode its values.
4. Fixtures in `docs/fixtures/` for mocking other teams' parts until integration.

## Workflow
1. Read your task file `.team/tasks/<ID>-<nn>.md`.
2. Build it inside your paths. Respect the timebox; if you hit it, ship what works and list the gaps.
3. Commit only your paths, one commit per task: `git add <your paths> && git commit -m "[W1-01] summary"`. No force-push, no `git add -A`, no rebases of others' work. Never commit `.env`, data files or `runs/`.
4. Append to `.team/status/<ID>.md`:
   ```
   DONE W1-01 (12:05): <one-line summary>. Test: <exact command(s)>. Gaps: <none | list>.
   ```
   or `BLOCKED W1-01 (12:05): <reason>`.
5. Tell the human "W1-01 done" (one line). The human relays to MANAGER and REVIEWER.
6. If your next task file already exists, start it immediately. Otherwise pick the next stretch item listed in your task file.

## Non-negotiables (the release is blocked if any is broken)
- Three separate LLM calls per round, never one call playing several roles.
- `MAX_ROUNDS = 3` enforced in code; round 3 is ballot only (no counters).
- The deterministic checker (H1–H7) overrides any agent agreement.
- The deterministic fallback works with the LLM switched off.
- Hash-chained, timestamped consensus log, viewable and downloadable.
- A real DOT row (`WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`) drives every scenario; every synthetic field is labelled.
- At least one failure case shown; eval numbers measured, not estimated.
- LLMs never compute numbers or check legality. Code does.
- Free-tier Gemini models (config.yaml). Handle HTTP 429 with back-off. Keys only in `.env`.

## Environment
- Python venv at repo root: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt` (W1 creates it in W1-01; others reuse it. If it doesn't exist yet when you start, create it yourself; it's gitignored).
- Raw data: `data/raw/flights.csv`, `data/raw/airlines.csv`, `data/raw/airports.csv` (the human places them; gitignored).
- API key: `.env` with `GEMINI_API_KEY=...` (the human creates it; gitignored).
- Run everything from the repo root; import as `from core.types import Scenario`, `from agents.coordinator import Coordinator`.
