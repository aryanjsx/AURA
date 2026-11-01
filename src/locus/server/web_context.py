"""Web search for chat messages.

When a chat request sets ``web_search``, the chat route searches the web for
the user's latest message before the model answers, reads the top pages, and
adds the results as context the model cites as ``[1]``, ``[2]``, ... The
sources are also sent to the client in a ``web_search`` SSE event so the UI
can link the citations.

Searching sends the query to the configured engine (DuckDuckGo, or Tavily,
You.com, Serply or Firecrawl with a key; see
:class:`locus.tools.web_search.WebSearchTool`), so the client only asks for it
when the user turns web search on. A message that contains a URL fetches that
page instead of searching.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Search results requested.
MAX_RESULTS = 5
#: Top results whose pages are fetched for more than the search snippet.
FETCH_TOP = 3
#: Characters kept from each fetched page.
PAGE_CHARS = 3000
SEARCH_TIMEOUT_S = 20.0
FETCH_TIMEOUT_S = 10.0

_RESULT_RE = re.compile(
    r"^###\s*(?P<title>.*?)\s*\nSource:\s*(?P<url>\S+)\s*\nSummary:\s*(?P<summary>.*)",
    re.S,
)


@dataclass
class WebSource:
    ref: int
    title: str
    url: str
    snippet: str = ""
    text: str = ""

    def public(self) -> Dict[str, Any]:
        """The fields sent to the client."""
        return {"ref": self.ref, "title": self.title, "url": self.url}


@dataclass
class WebSearchResult:
    query: str
    engine: str = ""
    sources: List[WebSource] = field(default_factory=list)
    error: Optional[str] = None

    def event(self) -> Dict[str, Any]:
        """Payload of the ``web_search`` SSE event."""
        payload: Dict[str, Any] = {
            "query": self.query,
            "engine": self.engine,
            "sources": [s.public() for s in self.sources],
        }
        if self.error:
            payload["error"] = self.error
        return payload


def parse_results(content: str) -> List[WebSource]:
    """Parse :class:`WebSearchTool`'s ``### title / Source / Summary`` blocks."""
    sources: List[WebSource] = []
    for block in content.split("\n\n---\n\n"):
        match = _RESULT_RE.match(block.strip())
        if not match:
            continue
        sources.append(
            WebSource(
                ref=len(sources) + 1,
                title=match["title"] or match["url"],
                url=match["url"],
                snippet=match["summary"].strip(),
            )
        )
    return sources


async def search_web(query: str) -> WebSearchResult:
    """Search for ``query`` and read the top pages. Never raises."""
    from locus.tools.web_search import WebSearchTool

    result = WebSearchResult(query=query)
    tool = WebSearchTool(max_results=MAX_RESULTS)
    try:
        found = await asyncio.wait_for(
            asyncio.to_thread(tool.execute, query=query), SEARCH_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        result.error = "The web search timed out."
        return result
    except Exception as exc:  # the tool reports most errors itself
        result.error = f"The web search failed ({type(exc).__name__})."
        return result

    metadata = found.metadata or {}
    result.engine = str(metadata.get("engine") or metadata.get("extractor") or "")
    if not found.success:
        result.error = found.content or "The web search failed."
        return result

    if metadata.get("mode") == "fetch":
        url = str(metadata.get("url", ""))
        result.sources = [
            WebSource(ref=1, title=url, url=url, text=found.content[: PAGE_CHARS * 2])
        ]
        return result

    result.sources = parse_results(found.content)
    if not result.sources:
        result.error = "The web search found no results."
        return result

    async def fetch(source: WebSource) -> None:
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(WebSearchTool._fetch_url, source.url, PAGE_CHARS),
                FETCH_TIMEOUT_S,
            )
            source.text = (text or "").strip()
        except Exception:
            logger.debug("Could not fetch %s", source.url, exc_info=True)

    await asyncio.gather(*(fetch(s) for s in result.sources[:FETCH_TOP]))
    return result


def render_context(result: WebSearchResult, today: Optional[_dt.date] = None) -> str:
    """The system prompt section that gives the model the search results."""
    today = today or _dt.date.today()
    if result.error or not result.sources:
        reason = result.error or "The web search found no results."
        return (
            "The user asked you to search the web, but the search didn't work: "
            f"{reason} Answer from your own knowledge, and say that you couldn't "
            "check the web, so recent details may be out of date."
        )
    lines = [
        "Web search results for the user's latest message, "
        f"retrieved {today.isoformat()}.",
        "Use them to answer. Cite the sources you rely on inline as [1], [2], "
        "and so on, using the numbers below. If the results don't answer the "
        "question, say so rather than guessing. Don't invent sources or URLs.",
        "",
    ]
    for source in result.sources:
        body = source.text or source.snippet
        lines.append(
            f"[{source.ref}] {source.title}\nURL: {source.url}\n{body}".rstrip()
        )
        lines.append("")
    return "\n".join(lines).rstrip()


__all__ = [
    "WebSearchResult",
    "WebSource",
    "parse_results",
    "render_context",
    "search_web",
]
