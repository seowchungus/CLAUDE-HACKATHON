# ACCORD BOARD

T0 = 11:09 · Now: 12:25 · Freeze 15:39 · Deadline 16:09 · Contracts: **FROZEN v1.1 (12:25)**
Rule (12:25, human): major decisions (new workers/roles, starting a major phase) need the human's approval. Tasks within a phase MANAGER delegates directly.

## Milestones
| Target | Milestone | Status |
|---|---|---|
| 11:39 | Contracts frozen, all workers started | ✅ 11:20 |
| 12:39 | W1 CLI milestone · W2 negotiation on fixture · W3 UI on mock | ✅ 12:10 (all three, ~30 min early) |
| 13:39–14:24 | **Integration** (INT-01) | ⏸ awaiting human approval; proposed start ~13:25 when wave 2 lands |
| 14:24–15:09 | Eval N=30 in background, chaos/kill/approve, map polish | ⏸ phase start needs approval |
| 15:09–15:39 | Fixes, README limitations, 2 hero scenarios cached | |
| 15:39 | **Feature freeze**; slides outline + pitch with real numbers | |

## Tasks
| ID | Owner | Title | Status | Depends | Timebox | Target |
|---|---|---|---|---|---|---|
| MGR-00 | MANAGER | Scaffold, config, CONTRACTS, fixtures, onboarding, tasks | done | — | 30 | 11:39 |
| MGR-03 | MANAGER | CONTRACTS v1.1 (REVIEWER-00 items 1–8), fixtures regenerated, models → 3.6 Flash | done | REVIEWER-00 | 15 | 12:25 |
| REVIEWER-00 | REVIEWER | Audit contracts + fixtures | done (CHANGES → v1.1) | MGR-00 | 15 | 11:40 |
| W1-01 | W1 | Types, config, hash-chained log, data prep | review | — | 35 | 11:55 |
| W1-02 | W1 | Scenario builder, metrics, option generator | review | W1-01 | 40 | 12:35 |
| W1-03 | W1 | Checker H1–H7, fallback, bundle, CLI milestone | review | W1-02 | 35 | 13:10 |
| W1-04 | W1 | Chaos, map payload, golden scenarios, eval skeleton | review | W1-03 | 30 | 13:40 |
| W2-01 | W2 | Schema, merged template A–E, Gemini client, kill switch | review | — | 45 | 12:00 |
| W2-02 | W2 | Coordinator state machine + log + events | review | W2-01 | 45 | 12:45 |
| W3-01 | W3 | API (mock) + console skeleton + negotiation room | review | — | 45 | 12:00 |
| W3-02 | W3 | Map, constraint wall, Gantt, log viewer | review | W3-01 | 45 | 12:45 |
| REVIEWER-01 | REVIEWER | Review wave 1 (W2 → W1 → W3) | todo | wave 1 | 40 | 13:20 |
| W1-05 | W1 | v1.1 alignment, scenario tension, hero candidates, eval LLM hook (mock only) | todo | v1.1 | 45 | 13:25 |
| W2-03 | W2 | v1.1 alignment, faster live runs, narrator, scripted failure modes | todo | v1.1 | 45 | 13:25 |
| W3-03 | W3 | v1.1 alignment, chaos/kill/approve controls, eval page, replay | todo | v1.1 | 45 | 13:25 |
| INT-01 | W3 lead (+W1, W2, REVIEWER) | Live integration + 10-step smoke test | **awaiting approval** | wave 2 | 45 | |

### Queued (needs phase approval)
- W1-06 live eval N=30 + B0/B1 (B2/B3 if quota), sharded across keys
- Hero cache: record 2 live hero runs to `api/hero_cache/`
- Fixes from REVIEWER-01 CHANGES (folded into the next tasks)

## Decisions & assumptions
- 12:25 Negotiators switched to `gemini-3.6-flash` (the proposal's named backup): 3.8 Flash timed out/503 on every call (W2-01). Parity kept. Backup = `gemini-flash-lite-latest`. README/pitch must say so.
- 12:25 CONTRACTS v1.1: additive fixes from REVIEWER-00 (see changelog). W2's agreement-set rule adopted as the contract.
- 12:25 Fixture bug (MANAGER's generator mutated a dict after hashing) fixed; fixtures regenerated.
- 12:10 Data: `data/raw/flights.csv` provided is PRE-FILTERED (358,774 rows, all qualifying). Banks, connections, AAR nominal and next-tail lookups only see delayed flights (undercount). **Open question to the human** (full Kaggle file or accept and disclose).
- 11:30 Workers commit their own paths per task (path-limited); destructive git commands banned.
- 11:17 Core types in `core/types.py` (W1), agent message types in `agents/schema.py` (W2).
- 11:17 Times are int minutes after local midnight; map positions labelled "estimated".
- 11:17 Chaos creates a NEW run (`parent_run_id`); v1.1: the parent is SUPERSEDED.

## Cuts applied
(none)

## Waiting on the human
- [ ] Approve starting **INT-01 (integration)** at ~13:25 (an hour ahead of plan) once W1-05/W2-03/W3-03 land
- [ ] Decide on the data: full `flights.csv` (Kaggle usdot/flight-delays) or accept the pre-filtered file with a disclosed limitation
- [ ] Extra Gemini keys (`GEMINI_API_KEY_2`, `_3`) before the eval phase
