"""Test that Exa screens result URLs through safe_public_result_url."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from deerflow.community import url_safety
from deerflow.community.exa import tools as exa_module


@pytest.fixture
def mock_config():
    """Mock config with Exa API key."""
    with patch("deerflow.community.exa.tools.get_app_config") as mock:
        config_obj = Mock()
        config_obj.model_extra = {"api_key": "test-key"}
        mock.return_value.get_tool_config.return_value = config_obj
        yield mock


def make_result(title, url, highlights=None):
    """Helper to create a result object matching Exa's structure."""
    return SimpleNamespace(title=title, url=url, highlights=highlights or [])


@pytest.mark.anyio
async def test_exa_imports_safe_public_result_url():
    """Exa must import the shared URL safety owner, not a local copy."""
    assert hasattr(exa_module, "_safe_public_url")
    assert exa_module._safe_public_url is url_safety.safe_public_result_url


@pytest.mark.anyio
@pytest.mark.parametrize(
    "hostile_url,expected_in_result",
    [
        ("http://127.0.0.1/admin", False),
        ("http://[::1]/internal", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("http://10.0.0.1/private", False),
        ("https://example.com/safe", True),
    ],
)
async def test_exa_web_search_screens_result_urls(mock_config, hostile_url, expected_in_result):
    """Exa web_search must screen result URLs; private/loopback/metadata URLs are dropped."""
    mock_response = SimpleNamespace(results=[make_result("Test", hostile_url, ["snippet"])])

    with patch("deerflow.community.exa.tools.Exa") as mock_exa:
        mock_client = Mock()
        mock_client.search.return_value = mock_response
        mock_exa.return_value = mock_client

        from deerflow.community.exa.tools import web_search_tool

        result = await web_search_tool.ainvoke({"query": "test query"})

        if expected_in_result:
            assert hostile_url in result
        else:
            assert hostile_url not in result


@pytest.mark.anyio
async def test_exa_web_search_preserves_safe_urls(mock_config):
    """Exa web_search must preserve safe public URLs unchanged."""
    safe_url = "https://example.com/article"
    mock_response = SimpleNamespace(results=[make_result("Article", safe_url, ["Good content"])])

    with patch("deerflow.community.exa.tools.Exa") as mock_exa:
        mock_client = Mock()
        mock_client.search.return_value = mock_response
        mock_exa.return_value = mock_client

        from deerflow.community.exa.tools import web_search_tool

        result = await web_search_tool.ainvoke({"query": "test"})

        assert safe_url in result
        assert "Article" in result


@pytest.mark.anyio
async def test_exa_web_search_drops_hostile_rows_without_raising(mock_config):
    """Mixed batches: drop only hostile URLs, keep safe ones, no exception."""
    results = [
        make_result("Private", "http://10.0.0.1/admin", ["bad"]),
        make_result("Safe", "https://example.com/good", ["good"]),
        make_result("Loopback", "http://127.0.0.1/secret", ["bad"]),
    ]
    mock_response = SimpleNamespace(results=results)

    with patch("deerflow.community.exa.tools.Exa") as mock_exa:
        mock_client = Mock()
        mock_client.search.return_value = mock_response
        mock_exa.return_value = mock_client

        from deerflow.community.exa.tools import web_search_tool

        result = await web_search_tool.ainvoke({"query": "test"})

        # Only the safe URL should remain
        assert "https://example.com/good" in result
        assert "10.0.0.1" not in result
        assert "127.0.0.1" not in result
