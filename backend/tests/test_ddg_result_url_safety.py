"""Tests for DDG search URL screening."""

from unittest.mock import MagicMock, patch

import pytest

from deerflow.community.ddg_search.tools import web_search_tool


@pytest.mark.anyio
async def test_ddg_web_search_screens_result_urls():
    """DDG web_search must screen result URLs for private/loopback addresses."""
    mock_results = [
        {"title": "Public", "href": "https://example.com/page", "body": "Safe result"},
        {"title": "Private IP", "href": "http://192.168.1.1/admin", "body": "Should drop"},
        {"title": "Loopback", "href": "http://127.0.0.1:8080/debug", "body": "Should drop"},
        {"title": "Metadata", "href": "http://169.254.169.254/latest/meta-data/", "body": "Should drop"},
    ]

    mock_config = MagicMock()
    mock_config.get_tool_config.return_value = None

    with (
        patch("deerflow.community.ddg_search.tools._search_text", return_value=mock_results),
        patch("deerflow.community.ddg_search.tools.get_app_config", return_value=mock_config),
    ):
        result_json = web_search_tool.invoke({"query": "test query"})

    import json

    output = json.loads(result_json)
    results = output["results"]
    assert len(results) == 1, f"Expected 1 safe result, got {len(results)}"
    assert results[0]["url"] == "https://example.com/page"
    assert "192.168" not in result_json
    assert "127.0.0.1" not in result_json
    assert "169.254" not in result_json


@pytest.mark.anyio
async def test_ddg_web_search_all_unsafe_returns_empty():
    """DDG web_search with all unsafe URLs returns no results."""
    mock_results = [
        {"title": "Private", "href": "http://10.0.0.1/", "body": "Unsafe"},
        {"title": "Local", "href": "http://localhost:3000/", "body": "Unsafe"},
    ]

    mock_config = MagicMock()
    mock_config.get_tool_config.return_value = None

    with (
        patch("deerflow.community.ddg_search.tools._search_text", return_value=mock_results),
        patch("deerflow.community.ddg_search.tools.get_app_config", return_value=mock_config),
    ):
        result_json = web_search_tool.invoke({"query": "test query"})

    import json

    output = json.loads(result_json)
    results = output["results"]
    assert isinstance(results, list)
    assert len(results) == 0
