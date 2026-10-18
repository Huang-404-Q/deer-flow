"""Tests for Brave Search URL screening."""

from unittest.mock import MagicMock, patch

import pytest

from deerflow.community.brave.tools import web_search_tool


@pytest.mark.anyio
async def test_brave_web_search_screens_result_urls():
    """Brave web_search must screen result URLs for private/loopback addresses."""
    mock_response = {
        "web": {
            "results": [
                {"title": "Public", "url": "https://example.com/page", "description": "Safe result"},
                {"title": "Private IP", "url": "http://192.168.1.1/admin", "description": "Should drop"},
                {"title": "Loopback", "url": "http://127.0.0.1:8080/debug", "description": "Should drop"},
                {"title": "Metadata", "url": "http://169.254.169.254/latest/meta-data/", "description": "Should drop"},
            ]
        }
    }

    mock_config = MagicMock()
    mock_config.get_tool_config.return_value = None

    with (
        patch("deerflow.community.brave.tools._brave_get", return_value=(mock_response, None)),
        patch("deerflow.community.brave.tools._get_api_key", return_value="test-key"),
        patch("deerflow.community.brave.tools.get_app_config", return_value=mock_config),
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
async def test_brave_web_search_all_unsafe_returns_empty():
    """Brave web_search with all unsafe URLs returns no results."""
    mock_response = {
        "web": {
            "results": [
                {"title": "Private", "url": "http://10.0.0.1/", "description": "Unsafe"},
                {"title": "Local", "url": "http://localhost:3000/", "description": "Unsafe"},
            ]
        }
    }

    mock_config = MagicMock()
    mock_config.get_tool_config.return_value = None

    with (
        patch("deerflow.community.brave.tools._brave_get", return_value=(mock_response, None)),
        patch("deerflow.community.brave.tools._get_api_key", return_value="test-key"),
        patch("deerflow.community.brave.tools.get_app_config", return_value=mock_config),
    ):
        result_json = web_search_tool.invoke({"query": "test query"})

    import json

    output = json.loads(result_json)
    # Brave returns error when no usable results
    assert "error" in output or (isinstance(output.get("results"), list) and len(output["results"]) == 0)
