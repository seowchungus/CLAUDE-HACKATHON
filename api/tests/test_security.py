"""Path-traversal regression tests for the SPA catch-all (W3-01-fix item 1)."""
import os

import pytest

os.environ.setdefault("MOCK", "1")

from fastapi.testclient import TestClient  # noqa: E402

from api import server  # noqa: E402

pytestmark = pytest.mark.skipif(not server.DIST.exists(), reason="web/dist not built (cd web && npm run build)")

SECRET_FILES = [server.ROOT / ".env", server.ROOT / "config.yaml", server.ROOT / "api" / "server.py"]
ATTACKS = [
    "/..%2f..%2f.env",
    "/..%2F..%2F.env",
    "/%2e%2e/%2e%2e/.env",
    "/%2e%2e%2f%2e%2e%2f.env",
    "/../config.yaml",
    "/../../.env",
    "/assets/../../.env",
    "/assets/..%2f..%2f.env",
    "/..%5c..%5c.env",
    "/%2fetc%2fpasswd",
    "//etc/passwd",
    "/....//....//.env",
    "/..%252f..%252f.env",
    "/../api/server.py",
]


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


def _secrets() -> list[bytes]:
    out = [p.read_bytes()[:200] for p in SECRET_FILES if p.exists()]
    if os.path.exists("/etc/passwd"):
        out.append(open("/etc/passwd", "rb").read()[:200])
    return out


@pytest.mark.parametrize("path", ATTACKS)
def test_no_file_outside_dist(client, path):
    r = client.get(path)
    body = r.content
    for s in _secrets():
        assert s not in body, f"{path} leaked a file outside web/dist"
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert body == (server.DIST / "index.html").read_bytes()


def test_safe_dist_file_rejects_escape():
    for p in ["../.env", "../../.env", "/etc/passwd", "assets/../../.env", "..", ""]:
        f = server.safe_dist_file(p)
        assert f is None or f.is_relative_to(server.DIST)
    assert server.safe_dist_file("index.html") == server.DIST / "index.html"


def test_index_still_served(client):
    r = client.get("/")
    assert r.status_code == 200 and b"<div id=\"root\">" in r.content
