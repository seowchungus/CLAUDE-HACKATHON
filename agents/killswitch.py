"""Process-global LLM kill switch. Checked before every LLM call and before every round."""
import threading

_lock = threading.Lock()
_enabled = True


def set_llm_enabled(enabled: bool) -> None:
    global _enabled
    with _lock:
        _enabled = bool(enabled)


def llm_enabled() -> bool:
    with _lock:
        return _enabled
