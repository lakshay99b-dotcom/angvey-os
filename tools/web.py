"""Web tools: multi-backend search crawler + page fetch."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .registry import ToolRegistry, ToolSpec

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _unwrap_ddg(href: str) -> str:
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return urllib.parse.unquote(qs["uddg"][0])
    return href


def _search_ddg_html(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    q = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    headers = {"User-Agent": UA}
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    for item in soup.select("div.result, div.results_links, div.web-result"):
        a = item.select_one("a.result__a, a.result-link, a[href]")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = _unwrap_ddg(a.get("href", ""))
        snippet_el = item.select_one("a.result__snippet, div.result__snippet, td.result-snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title and href.startswith("http"):
            results.append({"title": title, "url": href, "snippet": snippet, "source": "ddg"})
        if len(results) >= max_results:
            break
    if not results:
        for a in soup.select("a.result__a"):
            title = a.get_text(strip=True)
            href = _unwrap_ddg(a.get("href", ""))
            if title and href.startswith("http"):
                results.append({"title": title, "url": href, "snippet": "", "source": "ddg"})
            if len(results) >= max_results:
                break
    return results


def _search_wikipedia(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": max_results,
        "format": "json",
    }
    with httpx.Client(timeout=15) as client:
        resp = client.get(api, params=params, headers={"User-Agent": UA})
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
        results.append({"title": title, "url": page_url, "snippet": snippet, "source": "wikipedia"})
    return results


def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    max_results = max(1, min(int(max_results or 5), 10))
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        results.extend(_search_ddg_html(query, max_results))
    except Exception as e:
        errors.append(f"ddg: {e}")
    if len(results) < max_results:
        try:
            for w in _search_wikipedia(query, max_results):
                if not any(r.get("url") == w.get("url") for r in results):
                    results.append(w)
        except Exception as e:
            errors.append(f"wiki: {e}")
    if not results and errors:
        raise RuntimeError("Search failed: " + "; ".join(errors))
    return results[:max_results]


def fetch_webpage(url: str, max_chars: int = 4000) -> dict[str, Any]:
    headers = {"User-Agent": UA}
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
    return {"url": url, "title": title or url, "content": text, "chars": len(text)}


def register_web_tools(registry: ToolRegistry):
    registry.register(
        ToolSpec(
            name="web_search",
            description="Search the web for information. Returns titles, URLs and snippets from multiple sources.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Number of results 1-10", "default": 5},
                },
                "required": ["query"],
            },
            permissions=["READ"],
            risk_level="low",
            timeout=30,
        ),
        web_search,
    )
    registry.register(
        ToolSpec(
            name="fetch_webpage",
            description="Fetch and extract main text content from a webpage URL.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to fetch"},
                    "max_chars": {"type": "integer", "default": 4000},
                },
                "required": ["url"],
            },
            permissions=["READ"],
            risk_level="low",
            timeout=30,
        ),
        fetch_webpage,
    )
