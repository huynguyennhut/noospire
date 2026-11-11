import asyncio
from collections import deque
from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from backend.app.scanners.base import CancellationToken

logger = logging.getLogger("sentinel.crawler")

# Ignored asset extensions for queue expansion (static assets)
STATIC_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".css", ".js", ".mjs", ".woff", ".woff2", ".ttf", ".eot",
    ".svg", ".mp4", ".webm", ".mp3", ".wav", ".avi",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".exe", ".dmg",
)


@dataclass
class DiscoveredEndpoint:
    url: str
    depth: int
    status_code: int = 0
    content_type: str = ""
    content_length: int = 0
    title: Optional[str] = None
    links_found: int = 0
    error: Optional[str] = None


@dataclass
class CrawlResult:
    root_url: str
    target_domain: str
    total_pages_visited: int
    discovered_urls: List[str]
    endpoints: List[DiscoveredEndpoint]
    duration_seconds: float
    stopped_reason: str


class AsyncBFSCrawler:
    """Asynchronous Breadth-First Search (BFS) Web Crawler.
    Strictly constrained to the same-origin domain of the target asset.
    Features:
      - Bounded maximum depth (default: 3)
      - Bounded maximum page crawl count (default: 50)
      - Rate-limiting delay and bounded concurrency
      - Extraction of href, action, and src links from HTML
      - Cooperative cancellation via CancellationToken
    """

    def __init__(
        self,
        max_depth: int = 3,
        max_pages: int = 50,
        rate_limit_delay: float = 0.05,
        timeout: float = 8.0,
        user_agent: str = "NOOSFORGE-Security-Intelligence-Crawler/1.0 (+https://empire.edu.vn)",
        concurrency: int = 4,
    ) -> None:
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.user_agent = user_agent
        self.concurrency = concurrency

        self._href_regex = re.compile(r"""(?:href|src|action)\s*=\s*["']([^"'\s>]+)["']""", re.IGNORECASE)
        self._title_regex = re.compile(r"""<title(?:\s+[^>]*)?>([^<]+)</title>""", re.IGNORECASE)

    def is_same_origin(self, candidate_url: str, target_domain: str, target_port: Optional[int] = None) -> bool:
        """Enforces strict same-origin matching against target asset domain and port."""
        try:
            parsed = urlparse(candidate_url)
            if parsed.scheme.lower() not in ("http", "https"):
                return False
            cand_domain = parsed.hostname.lower() if parsed.hostname else ""
            if cand_domain != target_domain.lower():
                return False
            if target_port and parsed.port and parsed.port != target_port:
                return False
            return True
        except Exception:
            return False

    def is_static_asset(self, url: str) -> bool:
        """Determines if a URL points to a static media/asset file that shouldn't be parsed for HTML links."""
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in STATIC_EXTENSIONS)

    def extract_links(self, html_content: str, base_url: str, target_domain: str, target_port: Optional[int]) -> List[str]:
        """Extracts and normalizes all same-origin links found within an HTML document."""
        discovered: Set[str] = set()
        matches = self._href_regex.findall(html_content)
        for raw_link in matches:
            raw_link = raw_link.strip()
            if not raw_link or raw_link.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
                continue

            try:
                # Resolve relative URL against base URL and strip fragment
                resolved = urljoin(base_url, raw_link)
                clean_url, _ = urldefrag(resolved)

                # Strictly verify same-origin
                if self.is_same_origin(clean_url, target_domain, target_port):
                    discovered.add(clean_url)
            except Exception:
                continue

        return list(discovered)

    async def crawl(
        self,
        root_url: str,
        cancel_token: Optional[CancellationToken] = None,
        log_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> CrawlResult:
        """Executes the asynchronous same-origin BFS crawl."""
        start_time = time.time()
        parsed_root = urlparse(root_url)
        target_domain = parsed_root.hostname.lower() if parsed_root.hostname else ""
        target_port = parsed_root.port

        if not target_domain:
            raise ValueError(f"Invalid root URL locator: {root_url}")

        clean_root, _ = urldefrag(root_url)
        visited: Set[str] = set()
        all_discovered: Set[str] = {clean_root}
        endpoints: List[DiscoveredEndpoint] = []
        stopped_reason = "completed"

        # FIFO queue for Breadth-First Search: (url, depth)
        queue: deque[Tuple[str, int]] = deque([(clean_root, 0)])

        if log_callback:
            await log_callback(
                "crawler",
                f"Starting same-origin BFS crawl on {clean_root} [Domain: {target_domain}, Max Depth: {self.max_depth}, Max Pages: {self.max_pages}]"
            )

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=False,
            follow_redirects=True,
            headers=headers,
        ) as client:
            while queue and len(visited) < self.max_pages:
                if cancel_token and cancel_token.is_cancelled:
                    stopped_reason = "cancelled"
                    if log_callback:
                        await log_callback("crawler", "Crawl cancelled via CancellationToken.")
                    break

                current_url, current_depth = queue.popleft()

                if current_url in visited:
                    continue

                visited.add(current_url)

                # Rate limiting delay
                if self.rate_limit_delay > 0:
                    await asyncio.sleep(self.rate_limit_delay)

                try:
                    resp = await client.get(current_url)
                    content_type = resp.headers.get("content-type", "").lower()
                    content_length = len(resp.content)
                    status_code = resp.status_code

                    # Extract page title if available
                    title: Optional[str] = None
                    new_links: List[str] = []

                    if "html" in content_type:
                        title_match = self._title_regex.search(resp.text)
                        if title_match:
                            title = title_match.group(1).strip()

                        # Extract links if not at max depth and not static
                        if current_depth < self.max_depth and not self.is_static_asset(current_url):
                            new_links = self.extract_links(resp.text, str(resp.url), target_domain, target_port)
                            for link in new_links:
                                all_discovered.add(link)
                                if link not in visited and not any(link == q[0] for q in queue):
                                    if len(visited) + len(queue) < self.max_pages * 2:
                                        queue.append((link, current_depth + 1))

                    ep = DiscoveredEndpoint(
                        url=current_url,
                        depth=current_depth,
                        status_code=status_code,
                        content_type=content_type,
                        content_length=content_length,
                        title=title,
                        links_found=len(new_links),
                    )
                    endpoints.append(ep)

                    if log_callback and (len(visited) % 10 == 0 or len(visited) == 1):
                        await log_callback(
                            "crawler",
                            f"Crawled ({len(visited)}/{self.max_pages}): {current_url} [HTTP {status_code}, Depth {current_depth}]"
                        )

                except Exception as exc:
                    logger.debug(f"Crawler error on {current_url}: {exc}")
                    ep = DiscoveredEndpoint(
                        url=current_url,
                        depth=current_depth,
                        status_code=0,
                        error=str(exc),
                    )
                    endpoints.append(ep)

            if len(visited) >= self.max_pages:
                stopped_reason = "max_pages_reached"
            elif not queue and stopped_reason == "completed":
                stopped_reason = "queue_exhausted"

        duration = time.time() - start_time
        if log_callback:
            await log_callback(
                "crawler",
                f"Crawl finished in {duration:.2f}s: {len(visited)} pages visited, {len(all_discovered)} endpoints discovered ({stopped_reason})."
            )

        return CrawlResult(
            root_url=clean_root,
            target_domain=target_domain,
            total_pages_visited=len(visited),
            discovered_urls=sorted(list(all_discovered)),
            endpoints=endpoints,
            duration_seconds=round(duration, 2),
            stopped_reason=stopped_reason,
        )
