"""Per-run LLM request counting. One client may serve several runs at once (chaos child + parent),
so run_ended.n_llm_calls can't be a delta of client.n_calls. The coordinator opens a counter around
its gather; asyncio tasks inherit the context, and each client bumps the counter of the run it serves."""
import contextlib
from contextvars import ContextVar

_RUN_CALLS: ContextVar[list[int] | None] = ContextVar("accord_run_calls", default=None)


def bump(n: int = 1) -> None:
    """Called by a client once per real request (incl. retries)."""
    c = _RUN_CALLS.get()
    if c is not None:
        c[0] += n


@contextlib.contextmanager
def counting():
    """with counting() as c: ... -> c[0] = requests made inside this context (and tasks it starts)."""
    c = [0]
    token = _RUN_CALLS.set(c)
    try:
        yield c
    finally:
        _RUN_CALLS.reset(token)
