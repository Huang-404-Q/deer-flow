"""Test that Tavily screens result URLs through safe_public_result_url."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from deerflow.community import url_safety
from deerflow.community.tavily import tools as tavily_module


@pytest.fixture
def mock_config():
    """Mock config with Tavily API key."""
    with patch("deerflow.community.tavily.tools.get_app_config") as mock:
        config_obj = Mock()
        config_obj.model_extra = {"api_key": "test-key"}
        mock.return_value.get_tool_config.return_value = config_obj
        yield mock


@pytest.mark.anyio
async def test_tavily_imports_safe_public_result_url():
    """Tavily must import the shared URL safety owner, not a local copy."""
    assert hasattr(tavily_module, "_safe_public_url")
    assert tavily_module._safe_public_url is url_safety.safe_public_result_url


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
async def test_tavily_web_search_screens_result_urls(mock_config, hostile_url, expected_in_result):
    """Tavily web_search must screen result URLs; private/loopback/metadata URLs are dropped."""
    mock_client = AsyncMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "Test Result", "url": hostile_url, "content": "Test snippet"},
        ]
    }
    mock_client.close = AsyncMock()

    with patch("deerflow.community.tavily.tools.AsyncTavilyClient", return_value=mock_client):
        from deerflow.community.tavily.tools import web_search_tool

        result = await web_search_tool.ainvoke({"query": "test query"})

    # If URL was rejected, result should be empty list
    if expected_in_result:
        assert hostile_url in result
    else:
        # Result should not contain the hostile URL
        assert hostile_url not in result
        # Should return empty list, not an error
        assert result == "[]" or "[]" in result


@pytest.mark.anyio
async def test_tavily_web_search_preserves_safe_urls(mock_config):
    """Safe public URLs must pass through unchanged."""
    safe_url = "https://example.com/article"
    mock_client = AsyncMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "Safe Article", "url": safe_url, "content": "Content here"},
        ]
    }
    mock_client.close = AsyncMock()

    with patch("deerflow.community.tavily.tools.AsyncTavilyClient", return_value=mock_client):
        from deerflow.community.tavily.tools import web_search_tool

        result = await web_search_tool.ainvoke({"query": "test query"})

    assert safe_url in result
    assert "Safe Article" in result


@pytest.mark.anyio
async def test_tavily_web_search_drops_hostile_rows_without_raising(mock_config):
    """One hostile URL must not convert a valid search into a format error."""
    mock_client = AsyncMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "Safe", "url": "https://example.com/safe", "content": "Good"},
            {"title": "Hostile", "url": "http://127.0.0.1/admin", "content": "Bad"},
            {"title": "Also Safe", "url": "https://example.org/also-safe", "content": "Also Good"},
        ]
    }
    mock_client.close = AsyncMock()

    with patch("deerflow.community.tavily.tools.AsyncTavilyClient", return_value=mock_client):
        from deerflow.community.tavily.tools import web_search_tool

        result = await web_search_tool.ainvoke({"query": "test query"})

    # Must not raise; must return the two safe results
    assert "https://example.com/safe" in result
    assert "https://example.org/also-safe" in result
    assert "127.0.0.1" not in result
    assert "error" not in result.lower()
