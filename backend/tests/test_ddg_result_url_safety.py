"""Tests for DDG search URL screening."""

import json
import sys
from types import SimpleNamespace

import pytest

from deerflow.community.ddg_search import tools


def _install_fake_ddgs(monkeypatch: pytest.MonkeyPatch, results: list[dict]) -> None:
    """Exercise the public tool through the SDK boundary without network access."""

    class FakeDDGS:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        def text(self, query: str, **kwargs: object) -> list[dict]:
            return results

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    monkeypatch.setattr(tools, "get_app_config", lambda: SimpleNamespace(get_tool_config=lambda name: None))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/page", True),
        ("http://192.168.1.1/admin", False),
        ("http://127.0.0.1:8080/debug", False),
        ("http://169.254.169.254/latest/meta-data/", False),
    ],
)
def test_ddg_web_search_screens_result_urls(monkeypatch: pytest.MonkeyPatch, url: str, expected: bool) -> None:
    """The actual web_search tool returns only public result URLs."""
    _install_fake_ddgs(monkeypatch, [{"title": "Test", "href": url, "body": "Snippet"}])

    output = json.loads(tools.web_search_tool.invoke({"query": "test query"}))

    assert len(output["results"]) == int(expected)
    if expected:
        assert output["results"][0]["url"] == url
    else:
        assert url not in json.dumps(output)


def test_ddg_web_search_drops_only_unsafe_result_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mixed result set keeps the safe row and drops private and loopback URLs."""
    safe_url = "https://example.com/good"
    private_url = "http://10.0.0.1/admin"
    loopback_url = "http://localhost:3000/"
    _install_fake_ddgs(
        monkeypatch,
        [
            {"title": "Private", "href": private_url, "body": "Unsafe"},
            {"title": "Public", "href": safe_url, "body": "Safe"},
            {"title": "Loopback", "href": loopback_url, "body": "Unsafe"},
        ],
    )

    result_json = tools.web_search_tool.invoke({"query": "test query"})
    output = json.loads(result_json)

    assert output["total_results"] == 1
    assert output["results"][0]["url"] == safe_url
    assert private_url not in result_json
    assert loopback_url not in result_json
