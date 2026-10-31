# W3-01-fix: Review changes on W3-01/02 (SECURITY BLOCKER first)
Owner: W3 · Timebox: 20 min · **Priority: interrupt current work, do item 1 now** · Source: `.team/reviews/W3-01_02.md` (13:10)

1. **SECURITY (blocker for INT-01):** the SPA catch-all in `api/server.py` serves files outside `web/dist`: `GET /..%2f..%2f.env` returns `.env` (the API keys). Fix: resolve the requested path (`Path(DIST, p).resolve()`), require `resolved.is_relative_to(DIST.resolve())` and that it's a file, else serve `index.html` (or 404). Prefer FastAPI `StaticFiles(directory=DIST, html=True)` for assets. Regression tests: `/..%2f..%2f.env`, `/%2e%2e/%2e%2e/.env`, `/../config.yaml`, `/assets/../../.env` → never the file contents. Always bind `127.0.0.1` (document it in `api/README.md`; never `--host 0.0.0.0`).
2. Live `run_started.parent_run_id` is patched after logging, so the envelope doesn't match the log. Pass `parent_run_id` (and chaos) into the Coordinator so it is logged as emitted (coordinate with W2 if `Coordinator.__init__` needs a kwarg: BLOCKED line to MANAGER).
3. Live approve: map `{ok: false}` to HTTP 409 with the error; publish `coordinator.approved` on the stream even after the run ended.
4. Mock kill stream reuses one `log_hash` for every event; give each event its own entry/hash.
5. Type the `/chaos` request body as `ChaosEvent` (validation → 422 on bad kinds).

Commit item 1 on its own first (`[W3-01-fix] path traversal`), then the rest. Message MANAGER after item 1 is committed.
