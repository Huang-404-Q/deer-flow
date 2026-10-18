import logging
import re
import subprocess
import threading
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, uses_relative

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readabilipy import simple_json_from_html_string
from readabilipy.simple_json import have_node as _readabilipy_have_node

logger = logging.getLogger(__name__)

_READABILITY_JS_AVAILABLE: bool | None = None
_READABILITY_JS_PROBE_LOCK = threading.Lock()


class Article:
    url: str

    def __init__(self, title: str, html_content: str, url: str | None = None):
        self.title = title
        self.html_content = html_content
        self.url = url or ""

    def to_markdown(self, including_title: bool = True) -> str:
        markdown = ""
        if including_title:
            markdown += f"# {self.title}\n\n"

        if self.html_content is None or not str(self.html_content).strip():
            markdown += "*No content available*\n"
        else:
            markdown += md(self.html_content)

        return markdown

    def to_message(self) -> list[dict]:
        image_pattern = r"!\[.*?\]\((.*?)\)"

        content: list[dict[str, str]] = []
        markdown = self.to_markdown()

        if not markdown or not markdown.strip():
            return [{"type": "text", "text": "No content available"}]

        parts = re.split(image_pattern, markdown)

        for i, part in enumerate(parts):
            if i % 2 == 1:
                image_url = urljoin(self.url, part.strip())
                content.append({"type": "image_url", "image_url": {"url": image_url}})
            else:
                text_part = part.strip()
                if text_part:
                    content.append({"type": "text", "text": text_part})

        # If after processing all parts, content is still empty, provide a fallback message.
        if not content:
            content = [{"type": "text", "text": "No content available"}]

        return content


_BASE_TAG_RE = re.compile(r"<base", re.IGNORECASE)


def _resolve_html_urls(html: str, url: str) -> str:
    """Resolve destinations before extraction can discard the document's base tag."""
    # A base element requires a literal start-tag prefix. False positives in
    # comments or text elements still go through HTML5 tree construction.
    base = BeautifulSoup(html, "html5lib").find("base", href=True) if _BASE_TAG_RE.search(html) else None
    base_url = url
    if base is not None:
        try:
            candidate = urljoin(url, str(base["href"]).strip())
            # Keep only bases urljoin can resolve relative paths against.
            # Opaque bases fall back to the fetched URL; hierarchical FTP remains valid.
            if urlparse(candidate).scheme in uses_relative:
                base_url = candidate
        except ValueError:
            pass  # An invalid base must not prevent extraction of the page.
    resolver = _DestinationRewriter(html, base_url)
    resolver.feed(html)
    resolver.close()
    return resolver.result()


def _has_readability_js() -> bool:
    """Probe readabilipy's Node.js support once per process.

    ``readabilipy.have_node`` can try to install its JavaScript dependencies.
    Cache both outcomes and serialize the first probe so concurrent fetches do
    not repeat a failing npm lookup or race through the install path.
    """
    global _READABILITY_JS_AVAILABLE

    if _READABILITY_JS_AVAILABLE is not None:
        return _READABILITY_JS_AVAILABLE

    with _READABILITY_JS_PROBE_LOCK:
        if _READABILITY_JS_AVAILABLE is None:
            try:
                _READABILITY_JS_AVAILABLE = bool(_readabilipy_have_node())
            except Exception as exc:
                logger.warning("Readability.js availability probe failed (%s); using Python fallback", type(exc).__name__)
                _READABILITY_JS_AVAILABLE = False

    return _READABILITY_JS_AVAILABLE


def _link_preserving_python_fallback(html: str) -> dict[str, str | None]:
    """Extract a useful HTML section while retaining resolved link attributes.

    readabilipy's built-in Python tree fallback intentionally drops element
    attributes, including ``href`` and ``src``. Keeping the selected source
    HTML lets ``Article.to_markdown`` preserve the destinations resolved by
    :func:`_resolve_html_urls`.
    """
    soup = BeautifulSoup(html, "html5lib")
    title_node = soup.find("title") or soup.find("h1")
    title = title_node.get_text(" ", strip=True) if title_node else None
    content = soup.find("article") or soup.find("main") or soup.body or soup

    for node in content.find_all(["script", "style", "noscript", "template", "iframe", "nav", "footer", "aside", "form"]):
        node.decompose()

    return {"title": title or None, "content": str(content)}


# Tokenize attributes only inside a start tag identified by HTMLParser. Keeping
# source spans avoids rebuilding malformed markup before jsdom parses it.
_ATTRIBUTE_RE = re.compile(r"""([^\s/>=]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]*))?""")


class _DestinationRewriter(HTMLParser):
    # Treat link examples inside text-only elements as data, including nested
    # script-looking text; only the matching closing tag resumes tokenization.
    CDATA_CONTENT_ELEMENTS = ("script", "style", "textarea", "title", "xmp", "iframe", "noembed", "noframes", "plaintext")

    def __init__(self, html: str, base_url: str):
        super().__init__(convert_charrefs=False)
        self.html = html
        self.base_url = base_url
        self.text_element: str | None = None
        self.line_offsets = [0, *(match.end() for match in re.finditer("\n", html))]
        self.replacements: list[tuple[int, int, str]] = []

    def handle_starttag(self, tag, attrs):
        if self.text_element is not None:
            return
        if tag in {"textarea", "title", "xmp", "iframe", "noembed", "noframes", "plaintext"}:
            self.text_element = tag
            return
        attribute = {"a": "href", "img": "src"}.get(tag)
        if attribute is None:
            return
        raw = self.get_starttag_text()
        tag_end = re.match(r"<[^\s/>]+", raw).end()
        for match in _ATTRIBUTE_RE.finditer(raw, tag_end):
            if match.group(1).lower() != attribute:
                continue
            value = match.group(2)
            if value is not None:
                original = unescape(value[1:-1] if value.startswith(('"', "'")) else value)
                try:
                    resolved = urljoin(self.base_url, original.strip())
                except ValueError:
                    return
                if resolved != original:
                    line, column = self.getpos()
                    offset = self.line_offsets[line - 1] + column
                    self.replacements.append((offset + match.start(2), offset + match.end(2), '"' + escape(resolved, quote=True) + '"'))
            else:
                line, column = self.getpos()
                offset = self.line_offsets[line - 1] + column + match.end(1)
                self.replacements.append((offset, offset, '="' + escape(self.base_url, quote=True) + '"'))
            # Browsers use the first duplicate attribute, including a bare one.
            return

    def handle_endtag(self, tag):
        if tag == self.text_element and tag != "plaintext":
            self.text_element = None

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def result(self) -> str:
        parts = []
        cursor = 0
        for start, end, value in self.replacements:
            parts.extend((self.html[cursor:start], value))
            cursor = end
        parts.append(self.html[cursor:])
        return "".join(parts)


class ReadabilityExtractor:
    def extract_article(self, html: str, *, url: str | None = None) -> Article:
        if url:
            html = _resolve_html_urls(html, url)
        if _has_readability_js():
            try:
                article = simple_json_from_html_string(html, use_readability=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                stderr = getattr(exc, "stderr", None)
                if isinstance(stderr, bytes):
                    stderr = stderr.decode(errors="replace")
                stderr_info = f"; stderr={stderr.strip()}" if isinstance(stderr, str) and stderr.strip() else ""
                logger.warning(
                    "Readability.js extraction failed with %s%s; using link-preserving Python fallback",
                    type(exc).__name__,
                    stderr_info,
                    exc_info=True,
                )
                article = _link_preserving_python_fallback(html)
        else:
            article = _link_preserving_python_fallback(html)

        html_content = article.get("content")
        if not html_content or not str(html_content).strip():
            html_content = "No content could be extracted from this page"

        title = article.get("title")
        if not title or not str(title).strip():
            title = "Untitled"

        return Article(title=title, html_content=html_content, url=url)
