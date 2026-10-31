# INT-01 smoke (14:12)
LIVE VERDICT: **PASS**. W1-08 Part B (live eval, key 1) is unblocked.

## Live half (checked by REVIEWER on the run logs)
Three live runs, all on gemini-3.5-flash-lite, `scripted: false`:

| Run | Scenario | Agent positions (R1 / R2), latency in ms | Decision | Checker re-check | Chain verifies | LLM calls |
|---|---|---|---|---|---|---|
| 055918_630d25 | UA1575 DEN-ORD | 7376/7219/7175 · 8245/5985/7476 | CONSENSUS opt_3 | feasible | ok | 6 |
| 055941_228188 | DL2463 ICT-ATL | 7099/7645/8481 · 5775/5951/6040 | CONSENSUS opt_1 | feasible | ok | 6 |
| 060401_efb8a1 | OO6476 AUS-SFO | 1912/1980/1948 · 1375/1943/2004 | CONSENSUS opt_3 | feasible | ok | 6 |

- **3 separate agent positions per round, distinct latency_ms:** PASS. All 18 positions are `ok`.
- **Plan is feasible:** PASS. Re-checked independently with `core.bundle.build_bundle(...).checks`, which reports no failed constraints.
- **Chain verifies:** PASS. `core.log.verify_chain` returns `ok` on all 3 logs.
- **Budget ≤ 20 calls:** PASS. `budget_cli` shows GEMINI_API_KEY at 229/480, which is 18 calls since the 211 baseline. The cap was 231.

## Steps 1–10
- **Steps 1–4, 8, 9:** PASS. These are W3's HTTP smoke results, and the live evidence in the table above matches them.
- **Step 5 (veto or rejected counter):** PASS by human decision (14:05), using a workaround. None of the 3 live runs had a veto or a rejected counter. The human accepted the scripted golden run (OO6476: H3 and H4 vetoes, shown with the SCRIPTED badge) instead.
  - **Pitch/README caveat:** the eval must report the live `unsafe_proposals_blocked` count exactly as measured, even if it is 0.
- **Steps 6, 7, 10 (chaos, kill, offline):** PASS, as reported by W3 from mock and killed-LLM runs. These steps don't depend on the LLM.
  - The killed run (060007_11c572) ended in FALLBACK with `n_llm_calls` 0, and its chain verifies.

## Notes for the eval (W1-08 Part B)
- Starting point: 251 calls remain on key 1 against the 189 allocated. Keys _2 and _3 are at their cap.
- The free-tier day resets at 15:00 +08.
