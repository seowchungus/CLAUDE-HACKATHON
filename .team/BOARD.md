# ACCORD BOARD

T0 = 11:09 · Now: 15:05 · Freeze 15:39 · Deadline 16:09 · Contracts: **FROZEN v1.2 (12:55)**
Rule (12:25, human): major decisions (new workers/roles, starting a major phase) need the human's approval. Tasks within a phase MANAGER delegates directly.

## Milestones
| Target | Milestone | Status |
|---|---|---|
| 11:39 | Contracts frozen, all workers started | ✅ 11:20 |
| 12:39 | W1 CLI milestone · W2 negotiation on fixture · W3 UI on mock | ✅ 12:10 (all three, ~30 min early) |
| 13:39–14:24 | **Integration** (INT-01) | approved 12:58; starts when W1-06 + W2-04 pass review (~13:50) |
| 14:24–15:09 | Eval N=30 in background, chaos/kill/approve, map polish | ⏸ phase start needs approval |
| 15:09–15:39 | Fixes, README limitations, 2 hero scenarios cached | |
| 15:39 | **Feature freeze**; slides outline + pitch with real numbers | |

## Tasks
| ID | Owner | Title | Status | Depends | Timebox | Target |
|---|---|---|---|---|---|---|
| MGR-00 | MANAGER | Scaffold, config, CONTRACTS, fixtures, onboarding, tasks | done | — | 30 | 11:39 |
| MGR-03 | MANAGER | CONTRACTS v1.1 (REVIEWER-00 items 1–8), fixtures regenerated, models → 3.6 Flash | done | REVIEWER-00 | 15 | 12:25 |
| REVIEWER-00 | REVIEWER | Audit contracts + fixtures | done (CHANGES → v1.1) | MGR-00 | 15 | 11:40 |
| W1-01 | W1 | Types, config, hash-chained log, data prep | done ✅ (APPROVED 13:05) | — | 35 | 11:55 |
| W1-02 | W1 | Scenario builder, metrics, option generator | done ✅ (APPROVED 13:05) | W1-01 | 40 | 12:35 |
| W1-03 | W1 | Checker H1–H7, fallback, bundle, CLI milestone | done ✅ (APPROVED 13:05) | W1-02 | 35 | 13:10 |
| W1-04 | W1 | Chaos, map payload, golden scenarios, eval skeleton | done ✅ (APPROVED 13:05) | W1-03 | 30 | 13:40 |
| W2-01 | W2 | Schema, merged template A–E, Gemini client, kill switch | changes → W2-04 | — | 45 | 12:00 |
| W2-02 | W2 | Coordinator state machine + log + events | changes → W2-04 | W2-01 | 45 | 12:45 |
| W3-01 | W3 | API (mock) + console skeleton + negotiation room | changes → W3-01-fix | — | 45 | 12:00 |
| W3-02 | W3 | Map, constraint wall, Gantt, log viewer | changes → W3-01-fix | W3-01 | 45 | 12:45 |
| REVIEWER-01 | REVIEWER | Review wave 1 (W2 → W1 → W3) | done (W2 changes, W1 approved, W3 changes) | wave 1 | 40 | 13:20 |
| W1-05 | W1 | v1.1 alignment, eval hook, heroes | done ✅ (APPROVED, REVIEWER-02 W1-05_06) | v1.1 | 45 | 13:25 |
| W2-03 | W2 | v1.1 alignment, call accounting, narrator, scripted failure modes | done ✅ (W2-03_04 items 2–3 ✅) | v1.1 | 45 | 13:25 |
| W3-01-fix | W3 | SECURITY path traversal + 4 review items | done ✅ (items 1–5 ✅); MOCK approve item → W3-03-fix (b5c0ff6), re-review | REVIEWER | 20 | 13:30 |
| W3-03 | W3 | v1.1 alignment, chaos/kill/approve, eval page, replay | done (+W3-03-fix b5c0ff6), re-review | v1.1 | 45 | 13:25 |
| W1-06 | W1 | Adopt organisers' workbook limits | done ✅ (APPROVED, REVIEWER-02 W1-05_06) | v1.2 | 40 | 13:40 |
| W2-04 | W2 | Hard LLM call budget | CHANGES item 1 (ledger fail-open) → fixed in W2-04-fix3 (13:38), re-review | W2-03 | 35 | 13:45 |
| W3-04 | W3 | Challenge limits panel + LLM budget meter | review (b5c0ff6) | W3-03 | 25 | 13:50 |
| W1-07 | W1 | Role tension, frozen eval set, bad-day replay | review (3928d7b, b921633); REVIEWER's 3 WIP items addressed per W1 | W1-06 | 40 | 13:55 |
| REVIEWER-02 | REVIEWER | Review wave 2: W2-03+W2-04 → W1-05+W1-06 → W3-01-fix+W3-03 → W1-07 | todo | wave 2 | 30 | 13:55 |
| W3-05 | W3 | Eval page: mock ≠ MEASURED, bad-day card | review | W3-03 | 10 | 13:55 |
| W2-05 | W2 | INT-01 on-call + grounding check, per-run call count | review | W2-04 | 30 | 14:00 |
| W1-08 | W1 | A ✅ add3187 results.json = `--llm none`, n=30 · B: live eval N=30 | A review · B waits for EVAL RELEASED | W1-07, INT-01 | 10 + 45 | |
| W1-09 | W1 | Any flights.csv row → scenario_id (+ every row builds) | done (2ae2791; 784 rows, 0 crashes) | brief update | 10 | 15:20 |
| W3-07 | W3 | Pick ANY row in the console; heroes pinned; ?scenario= | done (c460ff0), live on :8000 | W1-09 | 20 | 15:30 |
| INT-01 | W3 lead | Live integration + smoke | in progress: live producer on real data with ACCORD_LLM=mock/killed (7dcd565); live Gemini smoke waits for the 20-call release | wave 2 | 45 | |

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

## Releases (human, 13:58)
- **INT-01 live smoke: RELEASED, max 20 calls** (key 1). W3: UA1575 + hero DL2463 ICT-ATL, then smoke step 10.
- **EVAL RELEASED (W1-08 Part B): max 189 calls, key 1 only, starts only after REVIEWER marks the INT-01 live smoke PASS.** Frozen set, sequential shard on key 1 (`--keys 1`). Stop at the cap and report the N actually run; no extrapolation. Target done ≤ 14:50.
- After the 15:00 reset (one fresh 480 for the project): hero recordings 20, demo + rehearsal 30, optional eval top-up toward N=30 only if done by 15:30.

## Decisions & assumptions
- 14:5x Updated challenge brief (clarifications): "pick ANY row of flights.csv", one turn = one message per agent, ≤3 turns then fallback with the reason logged; workbook values are synthetic. Only gap: the console offers a fixed list of 50 and the heroes aren't in it → W1-09 + W3-07. README cites the organisers' "synthetic planning limits" wording.
- 14:38 (human) **Re-run skipped.** W1-08c was blocked by W1's permission check (0 calls). We report the 18 flights that negotiated (18/18 consensus R2, 0 unsafe, 43% ungrounded, regret +1.0 J) and disclose the 12 LLM_ERROR rows (README + pitch). Quota after 15:00: hero recordings 20, rehearsal 30.
- 14:32 (human) W1-08b (655213e): all 12/30 fallbacks were LLM_ERROR ("Event loop is closed"; W2 fixed it in cac78e9 at 14:17, after the eval started). On the 18 rows where the agents actually negotiated, all 18 reached CONSENSUS in R2; unsafe blocked 0, executed 0; ungrounded 0.427. **Do not quote 0.60/0.40.** W1-08c: re-run the 12 rows NOW on today's remaining key-1 budget (~107 calls, stop at 480), note the first-pass bug in results.json, report the n that actually negotiated.
- 14:12 **INT-01 live smoke PASS** (REVIEWER, `.team/reviews/INT-smoke.md`): 3 live runs (UA1575, DL2463, OO6476), all CONSENSUS R2, feasible, chains verify; 18/20 calls (key 1 at 229/480). → W1-08 Part B (eval) unblocked.
- 14:05 (human) **Step 5 workaround:** none of the 3 live Flash-Lite runs showed a veto or rejected counter; step 5 accepted as PASS via the scripted golden OO6476 AUS-SFO (H3 + H4 vetoes, SCRIPTED badge). **Pitch wording: vetoes shown with scripted agents and counted in the measured eval; do not claim a live veto was shown.** The eval reports live `unsafe_proposals_blocked` exactly as measured, even if 0.
- 13:58 Heroes are now **2015-12-30_DL2463_ICT-ATL** (score 10) and **2015-03-02_OO6476_AUS-SFO**. WN2433 SMF-LAX was dropped as a hero (its golden is kept and excluded from eval). The eval set is frozen: `eval/eval_set.json`, sha256 4474f237…, N=30, committed before any eval run.
- 13:58 Bad day (deterministic only): ATL 2015-12-30, 438 arrivals. Compare B0 vs B1 only on rows where B1 has a feasible plan (`bad_day.B0_on_B1_planned`); B0's all-rows total looks cheaper partly because it breaks hard rules (161 infeasible). Pitch: B1 cuts bank delay 5443→2973 min at the cost of more misconnects and overtime.
- 13:58 Gate wait ≤ 30 min is our rule: added to `workbook_deviations` and the README.
- 13:22 Handover: work continues in a fresh clone (`~/Desktop/CLAUDE-HACKATHON`); new chats for W1/W2/W3/REVIEWER restart from task files + status. Fresh clone needs `data/raw/*` + `.env` before data-dependent tests (30 fail on missing `data/qualifying.parquet`; agents + api tests pass).
- 13:22 Commit 9f2af7d ("shaun's commit") swept several owners' paths, incl. W1-07 WIP in `core/` and a **mock** `eval/results.json` that the Eval page labels MEASURED. Fix: W3-05 (UI label), W1-08a (replace with `--llm none`). REVIEWER checks the core changes as part of W1-07.
- 13:10 Free-tier day resets 00:00 PT = **15:00 +08 today** (W2): every key returns to 0 → fresh 480/key for the 15:00–16:09 demo window. Plan: integration + eval on today's remaining budget; demo/rehearsal after 15:00.
- 13:10 Legacy `ramp_overtime_hard_cap_min` removed; `min_turnaround_min` kept only as the fallback for fixture scenarios without workbook limits.
- 13:10 Security: REVIEWER found a path traversal serving `.env` via the API catch-all. The only running server was bound to 127.0.0.1:8001 (checked), so no off-machine exposure. Fix is a hard gate for INT-01; servers bind 127.0.0.1 only.
- 13:05 Pitch/README wording (REVIEWER): status-quo cost is computed over the organisers' delayed-only file, so say "across the N qualifying delayed flights in the provided 2015 DOT data", never "all 2015 flights".
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
- [x] Keys 2 and 3 are in the **same project** as key 1 (human, 13:57): no extra capacity; pinned at cap in the ledger and config. Eval runs on key 1 only.
- [ ] Key 1 dashboard reading → `budget_cli --set GEMINI_API_KEY=<n>`
