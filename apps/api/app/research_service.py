from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx


@dataclass
class SearchResult:
    query: str
    title: str
    url: str
    snippet: str = ""


def _plain_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _direct_url(value: str) -> str:
    parsed = urlparse(html.unescape(value))
    redirect = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(redirect) if redirect else html.unescape(value)


def search_public_web(queries: list[str], limit_per_query: int = 5) -> dict:
    """Search DuckDuckGo's HTML endpoint without requiring a second API key.

    Results are candidates only. A following LLM curation node decides whether a
    candidate satisfies the course source policy before it is written to the
    course workspace.
    """
    results: list[SearchResult] = []
    errors: list[str] = []
    headers = {"User-Agent": "AI-Course-Agent/0.1 (+local research workflow)"}
    with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
        for query in queries[:6]:
            try:
                response = client.get("https://html.duckduckgo.com/html/", params={"q": query})
                response.raise_for_status()
                matches = re.findall(
                    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                    response.text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                for href, label in matches[:limit_per_query]:
                    url = _direct_url(href)
                    if not url.startswith(("http://", "https://")):
                        continue
                    results.append(SearchResult(query=query, title=_plain_html(label), url=url))
            except httpx.HTTPError as exc:
                errors.append(f"{query}: {str(exc)[:180]}")
    unique: dict[str, SearchResult] = {}
    for result in results:
        unique.setdefault(result.url, result)
    return {
        "queries": queries,
        "results": [asdict(item) for item in list(unique.values())[:24]],
        "errors": errors,
    }
