"""Tests for readability extraction fallback behavior."""

import subprocess

import pytest

from deerflow.utils.readability import Article, ReadabilityExtractor


def test_extract_article_falls_back_when_readability_js_fails(monkeypatch):
    """A Node extraction error falls back without losing resolved link targets."""

    calls: list[bool] = []

    monkeypatch.setattr("deerflow.utils.readability._has_readability_js", lambda: True)

    def _fake_simple_json_from_html_string(html: str, use_readability: bool = False):
        calls.append(use_readability)
        if use_readability:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=["node", "ExtractArticle.js"],
                stderr="boom",
            )
        pytest.fail("The link-preserving fallback should not call readabilipy's attribute-stripping path")

    monkeypatch.setattr(
        "deerflow.utils.readability.simple_json_from_html_string",
        _fake_simple_json_from_html_string,
    )

    article = ReadabilityExtractor().extract_article(
        '<html><head><title>Fallback Title</title></head><body><article><p>Fallback <a href="../next">Content</a></p></article></body></html>',
        url="https://example.com/docs/current",
    )

    assert calls == [True]
    assert article.title == "Fallback Title"
    assert "[Content](https://example.com/next)" in article.to_markdown()


def test_extract_article_uses_link_preserving_fallback_when_node_is_unavailable(monkeypatch):
    from deerflow.utils import readability

    monkeypatch.setattr(readability, "_has_readability_js", lambda: False)
    monkeypatch.setattr(
        readability,
        "simple_json_from_html_string",
        lambda *args, **kwargs: pytest.fail("readabilipy should not run without its Node extractor"),
    )

    article = ReadabilityExtractor().extract_article(
        '<html><body><article><p>Fallback <a href="../next">Content</a></p></article></body></html>',
        url="https://example.com/docs/current",
    )

    assert "[Content](https://example.com/next)" in article.to_markdown()


def test_readability_node_availability_probe_is_cached(monkeypatch):
    from deerflow.utils import readability

    calls = 0

    def unavailable():
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(readability, "_READABILITY_JS_AVAILABLE", None)
    monkeypatch.setattr(readability, "_readabilipy_have_node", unavailable)

    assert readability._has_readability_js() is False
    assert readability._has_readability_js() is False
    assert calls == 1


def test_extract_article_re_raises_unexpected_exception(monkeypatch):
    """Unexpected errors should be surfaced instead of silently falling back."""

    calls: list[bool] = []
    monkeypatch.setattr("deerflow.utils.readability._has_readability_js", lambda: True)

    def _fake_simple_json_from_html_string(html: str, use_readability: bool = False):
        calls.append(use_readability)
        if use_readability:
            raise RuntimeError("unexpected parser failure")
        return {"title": "Should Not Reach Fallback", "content": "<p>Fallback</p>"}

    monkeypatch.setattr(
        "deerflow.utils.readability.simple_json_from_html_string",
        _fake_simple_json_from_html_string,
    )

    with pytest.raises(RuntimeError, match="unexpected parser failure"):
        ReadabilityExtractor().extract_article("<html><body>test</body></html>")
    assert calls == [True]


def test_article_to_message_with_images():
    """Article.to_message should handle articles containing images without AttributeError."""
    # Absolute image URL without source url
    art_abs = Article("Test Image", '<img src="https://example.com/pic.png">')
    msg_abs = art_abs.to_message()
    assert any(block.get("type") == "image_url" and block["image_url"]["url"] == "https://example.com/pic.png" for block in msg_abs)

    # Relative image URL with source url
    art_rel = Article("Test Relative Image", '<img src="/assets/pic.png">', url="https://example.com/base/")
    msg_rel = art_rel.to_message()
    assert any(block.get("type") == "image_url" and block["image_url"]["url"] == "https://example.com/assets/pic.png" for block in msg_rel)
