# ACCORD BOARD

T0 = 11:09 · Now: 12:55 · Freeze 15:39 · Deadline 16:09 · Contracts: **FROZEN v1.2 (12:55)**
Rule (12:25, human): major decisions (new workers/roles, starting a major phase) need the human's approval. Tasks within a phase MANAGER delegates directly.

## Milestones
| Target | Milestone | Status |
|---|---|---|
| 11:39 | Contracts frozen, all workers started | ✅ 11:20 |
| 12:39 | W1 CLI milestone · W2 negotiation on fixture · W3 UI on mock | ✅ 12:10 (all three, ~30 min early) |
| 13:39–14:24 | **Integration** (INT-01) | ⏸ awaiting human approval; start when W1-06 + W2-04 land (~13:45) |
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
| REVIEWER-01 | REVIEWER | Review wave 1 (W2 → W1 → W3) | doing | wave 1 | 40 | 13:20 |
| W1-05 | W1 | v1.1 alignment (§1), eval hook mock-only (§4); §2 replaced by W1-06; §3 after W1-06 | doing | v1.1 | 45 | 13:25 |
| W2-03 | W2 | v1.1 alignment, call accounting (freeze), narrator, scripted failure modes | doing | v1.1 | 45 | 13:25 |
| W3-03 | W3 | v1.1 alignment, chaos/kill/approve controls, eval page, replay | doing | v1.1 | 45 | 13:25 |
| W1-06 | W1 | Adopt organisers' workbook limits (replaces W1-05 §2/§3 order) | todo | v1.2 | 40 | 13:40 |
| W2-04 | W2 | Hard LLM call budget (ledger, RPM, no cascade), Flash-Lite, workbook charters | todo | W2-03 | 35 | 13:45 |
| W3-04 | W3 | Challenge limits panel + LLM budget meter | todo | W3-03 | 25 | 13:50 |
| INT-01 | W3 lead (+W1, W2, REVIEWER) | Live integration + 10-step smoke test | approved 12:58 (starts when W1-06 + W2-04 are reviewed) | wave 2 | 45 | |

### Queued (needs phase approval)
- W1-06 live eval N=30 + B0/B1 (B2/B3 if quota), sharded across keys
- Hero cache: record 2 live hero runs to `api/hero_cache/`
- Fixes from REVIEWER-01 CHANGES (folded into the next tasks)

## LLM budget (Gemini 3.5 Flash Lite, main key): 500/day, 211 used at 12:45 → cap 480 → **269 usable today**
| Allocation | Calls | Released? |
|---|---|---|
| Integration smoke (INT-01) | 20 | no |
| Hero recordings (2 runs) | 20 | no |
| Demo + rehearsal | 30 | no |
| Eval (N≈20–25 on one key; N=30 with a 2nd key) | 189 | no |
| Reserve | 10 | — |
Enforced in code by `agents/budget.py` (W2-04). QUOTA FREEZE: no live calls until MANAGER releases an allocation.

## Decisions & assumptions
- 12:58 Wave 2 had not started by 12:57 (relay gap). MANAGER now messages sessions directly (human-approved).
- 12:50 (human) Organisers' workbook `challenge2_operational_constraints.xlsx` adopted as is. No external/full flights file. Deviations listed in `config.yaml: workbook_deviations`, shown in UI + README.
- 12:50 (human) All agents on Gemini 3.5 Flash Lite; limits must never be exceeded → hard budget guard; no backup-model cascade; narrator = template (0 calls).
- 12:25 Negotiators switched to `gemini-3.6-flash` (the proposal's named backup): 3.8 Flash timed out/503 on every call (W2-01). Parity kept. Backup = `gemini-flash-lite-latest`. README/pitch must say so.
- 12:25 CONTRACTS v1.1: additive fixes from REVIEWER-00 (see changelog). W2's agreement-set rule adopted as the contract.
- 12:25 Fixture bug (MANAGER's generator mutated a dict after hashing) fixed; fixtures regenerated.
- 12:10 Data: provided `flights.csv` = delayed-only (358,774 rows, all qualifying, no Oct, no cancelled/diverted). Explained by the workbook (12:45): intentional; capacity limits come from the workbook. Resolved: keep it, disclose "October 2015 not in provided data".
- 11:30 Workers commit their own paths per task (path-limited); destructive git commands banned.
- 11:17 Core types in `core/types.py` (W1), agent message types in `agents/schema.py` (W2).
- 11:17 Times are int minutes after local midnight; map positions labelled "estimated".
- 11:17 Chaos creates a NEW run (`parent_run_id`); v1.1: the parent is SUPERSEDED.

## Cuts applied
- 12:55 Narrator LLM → deterministic template (cut #2, quota).
- 12:55 Model ablation B3 skipped (cut #7, quota). B2 single-agent ablation only if a 2nd key appears.

## Waiting on the human
- [x] INT-01 approved 12:58 ("proceed with the next step"); starts when W1-06 + W2-04 pass review
- [x] Data decided (12:50): provided file + workbook
- [x] Keys 2 and 3 in `.env` (12:57)
- [ ] Dashboard usage for keys 2 and 3, and confirmation they are in **different projects** from key 1 (placeholders of 250 used each until then)
