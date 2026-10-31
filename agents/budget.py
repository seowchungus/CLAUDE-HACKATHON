"""Hard LLM call budget (CONTRACTS v1.2 §4.4). The free-tier limits must never be exceeded.

Ledger `runs/llm_budget.json` = {date_pacific, keys: {ENV_NAME: used}, recent: {ENV_NAME: [epoch_s...]}},
shared by every process (server, eval, CLIs) under an exclusive fcntl lock. The day rolls over at
midnight America/Los_Angeles. A new ledger starts each key at llm_budget.used_before_ledger (loud warning).
A corrupt ledger fails CLOSED: every reserve is refused until a human repairs it with budget_cli --set.
Only env-var NAMES are stored or printed, never the keys themselves.
"""
import asyncio
import contextlib
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from core.config import load_config, repo_path

RPM_WINDOW_S = 60.0


class LLMBudget(BaseModel):
    keys: dict[str, dict]   # key env name -> {used_today, cap, remaining, rpm_cap}; never the key itself
    enforce: bool
    resets_at: str          # ISO time of the next daily reset


LEDGER_ENV = "ACCORD_LLM_LEDGER"   # overrides llm_budget.ledger (tests point it at a tmp file)


class LedgerCorrupt(Exception):
    """The ledger exists but can't be read: the count is unknown, so nothing may be reserved."""


def _bcfg(cfg: dict | None) -> dict:
    b = dict((cfg or load_config())["llm_budget"])
    if os.environ.get(LEDGER_ENV):
        b["ledger"] = os.environ[LEDGER_ENV]
    return b


def _tz(b: dict) -> ZoneInfo:
    return ZoneInfo(b.get("daily_reset_tz", "America/Los_Angeles"))


def _day(b: dict, now: float) -> str:
    return datetime.fromtimestamp(now, _tz(b)).strftime("%Y-%m-%d")


def next_reset(b: dict, now: float) -> datetime:
    local = datetime.fromtimestamp(now, _tz(b))
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


@contextlib.contextmanager
def _ledger(b: dict, now: float, repair: bool = False):
    """Exclusive, cross-process access to the ledger; yields the dict and writes it back atomically.
    Raises LedgerCorrupt on an unreadable ledger (left untouched) unless repair=True (budget_cli --set)."""
    path = repo_path(b["ledger"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".lock", "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = None
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
                        raise ValueError("ledger has no 'keys' object")
                except ValueError as e:
                    if not repair:
                        print(f"LLM_BUDGET ledger {path} is corrupt ({e}); refusing every LLM call until "
                              "repaired with: python -m agents.budget_cli --set GEMINI_API_KEY=<n>", file=sys.stderr)
                        raise LedgerCorrupt(str(e)) from e
                    data = None
            today = _day(b, now)
            if data is None:   # new ledger: start from today's dashboard readings
                print(f"LLM_BUDGET new ledger {path} seeded from config readings "
                      f"{b.get('used_before_ledger')}; correct with budget_cli --set", file=sys.stderr)
                data = {"date_pacific": today, "keys": dict(b.get("used_before_ledger") or {}), "recent": {}}
            elif data.get("date_pacific") != today:   # Pacific midnight passed: fresh daily quota
                data = {"date_pacific": today, "keys": {k: 0 for k in data.get("keys", {})}, "recent": {}}
            data.setdefault("recent", {})
            yield data
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, sort_keys=True)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _try_reserve(data: dict, b: dict, key_name: str, now: float, check_rpm: bool) -> tuple[str, int, float]:
    """-> (outcome "ok" | "daily" | "rpm", used, rpm_wait_s). Mutates data only on "ok"."""
    cap = int(b["per_key_daily_cap"])
    used = int(data["keys"].get(key_name, 0))
    if b.get("enforce", True) and used >= cap:
        return "daily", used, 0.0
    recent = [t for t in data["recent"].get(key_name, []) if now - t < RPM_WINDOW_S]
    if check_rpm and b.get("enforce", True) and len(recent) >= int(b["per_key_rpm_cap"]):
        data["recent"][key_name] = recent
        return "rpm", used, RPM_WINDOW_S - (now - min(recent)) + 0.05
    recent.append(now)
    data["recent"][key_name] = recent
    data["keys"][key_name] = used + 1
    return "ok", used + 1, 0.0


def reserve_ex(key_name: str, cfg: dict | None = None, now: float | None = None) -> tuple[bool, int, int]:
    """Atomically count one request against the daily cap. -> (allowed, used_after, cap)."""
    b = _bcfg(cfg)
    now = time.time() if now is None else now
    try:
        with _ledger(b, now) as data:
            outcome, used, _ = _try_reserve(data, b, key_name, now, check_rpm=False)
    except LedgerCorrupt:
        return False, int(b["per_key_daily_cap"]), int(b["per_key_daily_cap"])
    return outcome == "ok", used, int(b["per_key_daily_cap"])


def reserve(key_name: str, cfg: dict | None = None, now: float | None = None) -> bool:
    """Contract §4.4: called before EVERY real request incl. retries. False -> refuse (rate_limited)."""
    return reserve_ex(key_name, cfg, now)[0]


async def acquire(key_name: str, cfg: dict | None = None, clock=time.time,
                  sleep=asyncio.sleep) -> tuple[bool, int, int]:
    """reserve() plus the per-key RPM limiter (sliding 60 s window, shared via the ledger).
    Waits for a free slot instead of erroring; returns (allowed, used_after, cap)."""
    b = _bcfg(cfg)
    while True:
        now = clock()
        try:
            with _ledger(b, now) as data:
                outcome, used, wait = _try_reserve(data, b, key_name, now, check_rpm=True)
        except LedgerCorrupt:
            return False, int(b["per_key_daily_cap"]), int(b["per_key_daily_cap"])
        if outcome != "rpm":
            return outcome == "ok", used, int(b["per_key_daily_cap"])
        await sleep(wait)


def budget_status(cfg: dict | None = None, now: float | None = None) -> LLMBudget:
    b = _bcfg(cfg)
    now = time.time() if now is None else now
    cap = int(b["per_key_daily_cap"])
    try:
        with _ledger(b, now) as data:
            used = dict(data["keys"])
    except LedgerCorrupt:   # unknown count -> report every key as exhausted
        used = {n: cap for n in (b.get("used_before_ledger") or {})}
    names = list(dict.fromkeys([*(b.get("used_before_ledger") or {}), *used]))
    keys = {n: {"used_today": int(used.get(n, 0)), "cap": cap, "remaining": max(0, cap - int(used.get(n, 0))),
                "rpm_cap": int(b["per_key_rpm_cap"])} for n in names}
    return LLMBudget(keys=keys, enforce=bool(b.get("enforce", True)), resets_at=next_reset(b, now).isoformat())


def remaining(key_names: list[str], cfg: dict | None = None, now: float | None = None) -> int:
    st = budget_status(cfg, now)
    return sum(st.keys.get(n, {"remaining": int(_bcfg(cfg)["per_key_daily_cap"])})["remaining"] for n in key_names)


def set_used(key_name: str, n: int, cfg: dict | None = None, now: float | None = None) -> None:
    """Correct the ledger to the dashboard reading (MANAGER/human use only)."""
    b = _bcfg(cfg)
    now = time.time() if now is None else now
    with _ledger(b, now, repair=True) as data:
        data["keys"][key_name] = int(n)
