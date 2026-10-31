"""Config loader. Values come from config.yaml; never hardcode them elsewhere."""
import copy
import functools
import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@functools.lru_cache(maxsize=8)
def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(path: str = "config.yaml") -> dict:
    """Load config.yaml (cached). Relative paths resolve against the repo root. Returns a copy."""
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(REPO_ROOT, path)
    return copy.deepcopy(_load(os.path.abspath(path)))


def repo_path(rel: str) -> str:
    """Absolute path for a repo-relative path (so code works from any cwd)."""
    return rel if os.path.isabs(rel) else os.path.join(REPO_ROOT, rel)
