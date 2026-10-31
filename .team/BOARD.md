# ACCORD BOARD

T0 = 11:09 · Now: 11:18 · Freeze 15:39 · Deadline 16:09 · Contracts: **FROZEN v1.0 (11:20)**

## Milestones
| Target | Milestone | Status |
|---|---|---|
| 11:39 | Contracts frozen, all workers started | contracts done 11:17; workers starting |
| 12:39 | W1 CLI milestone · W2 negotiation on fixture · W3 UI on mock | |
| 13:39–14:24 | **Integration**: live coordinator → SSE → console (integration tasks only) | |
| 14:24–15:09 | Eval N=30 in background, chaos/kill/approve, map polish | |
| 15:09–15:39 | Fixes, README limitations, 2 hero scenarios cached | |
| 15:39 | **Feature freeze**; slides outline + pitch with real numbers | |

## Tasks
| ID | Owner | Title | Status | Depends | Timebox | Target |
|---|---|---|---|---|---|---|
| MGR-00 | MANAGER | Scaffold, config, CONTRACTS, fixtures, onboarding, tasks | done | — | 30 | 11:39 |
| REVIEWER-00 | REVIEWER | Audit contracts + fixtures | todo | MGR-00 | 15 | 11:40 |
| W1-01 | W1 | Types, config, hash-chained log, data prep | todo | data files | 35 | 11:55 |
| W1-02 | W1 | Scenario builder, metrics, option generator | todo | W1-01 | 40 | 12:35 |
| W1-03 | W1 | Checker H1–H7, fallback, bundle, CLI milestone | todo | W1-02 | 35 | 13:10 |
| W1-04 | W1 | Chaos, map payload, golden scenarios (+eval skeleton stretch) | todo | W1-03 | 30 | 13:40 |
| W2-01 | W2 | Schema, merged template A–E, Gemini client, kill switch | todo | fixtures | 45 | 12:00 |
| W2-02 | W2 | Coordinator state machine + log + events | todo | W2-01, W1-01 (log) | 45 | 12:45 |
| W3-01 | W3 | API (mock) + console skeleton + negotiation room | todo | fixtures | 45 | 12:00 |
| W3-02 | W3 | Map, constraint wall, Gantt, log viewer | todo | W3-01 | 45 | 12:45 |

### Queued (written when the stream gets there)
- W2-03 narrator + Resolution Record; grounding check (stretch, cut #1)
- W3-03 chaos / kill / approve controls polish + eval results page + replay badge
- INT-01..03 integration (13:39): api live mode on Coordinator + core.bundle; golden scenarios in UI
- W1-05 eval/run_eval.py N=30 + B0/B1 (+B2/B3 if quota), split across keys
- Hero cache: 2 scenarios recorded to `api/hero_cache/`

## Decisions & assumptions
- 11:17 Core types live in `core/types.py` (W1), agent message types in `agents/schema.py` (W2), per CONTRACTS.md. The proposal's single `schema.py` is split by owner.
- 11:17 Times are int minutes after local midnight (DOT times are local; map positions are labelled "estimated").
- 11:17 FP grid = `as_filed, speed_reduction, hold_10, hold_20, reroute_weather`.
- 11:17 Chaos creates a NEW run on the mutated scenario (`parent_run_id` links them), rather than mutating a run in flight.
- 11:17 Model strings in config.yaml (`gemini-3.8-flash`, `gemini-flash-lite-latest`, `gemini-3.6-flash`) are unverified; W2-01 checks them.
- 11:17 Shared fixtures in `docs/fixtures/` (MANAGER) are hand-made, `fixture: true`, not real rows.
- 11:17 `requirements.txt`, `.gitignore`, `.env.example` owned by MANAGER.

## Cuts applied
(none)

## Waiting on the human
- [ ] `data/raw/flights.csv`, `airlines.csv`, `airports.csv` (from `Challenge #2\DATA`)
- [ ] `.env` with `GEMINI_API_KEY` (plus `_2`, `_3` from teammates for the eval)
- [ ] Challenge PDFs into `docs/challenge/` if available (optional)
