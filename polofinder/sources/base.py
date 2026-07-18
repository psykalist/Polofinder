"""Base class for every site adapter."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from ..models import Listing


@dataclass
class SourceResult:
    """What a source reports back - including why it found nothing."""
    key: str
    name: str
    homepage: str
    status: str                      # OK | BLOCKED_ROBOTS | DEEPLINK_ONLY | ERROR | DISABLED
    listings: List[Listing] = field(default_factory=list)
    search_url: Optional[str] = None   # the human-clickable filtered search
    detail: str = ""                   # explanation shown in the report
    duration_s: float = 0.0

    @property
    def count(self) -> int:
        return len(self.listings)


class Source:
    key = "base"
    name = "Base"
    homepage = ""
    # If True, this site's robots.txt blocks filtered search and we ship a
    # deep link rather than scraping (unless respect_robots is turned off).
    deeplink_only = False
    robots_note = ""

    def __init__(self, cfg: dict, robots, browser=None):
        self.cfg = cfg
        self.robots = robots
        self.browser = browser

    # --- to be implemented by subclasses ---
    def search_url(self) -> str:
        raise NotImplementedError

    def fetch(self) -> List[Listing]:
        return []

    # --- shared plumbing ---
    def run(self) -> SourceResult:
        started = time.time()
        url = None
        try:
            url = self.search_url()
        except Exception:
            pass

        result = SourceResult(
            key=self.key, name=self.name, homepage=self.homepage,
            status="OK", search_url=url,
        )

        respect = self.cfg["sources"].get("respect_robots", True)

        if self.deeplink_only and respect:
            result.status = "DEEPLINK_ONLY"
            result.detail = self.robots_note or "robots.txt disallows filtered search"
            result.duration_s = time.time() - started
            return result

        if url and respect and not self.robots.allowed(url):
            result.status = "BLOCKED_ROBOTS"
            result.detail = "robots.txt disallows this search URL"
            result.duration_s = time.time() - started
            return result

        try:
            result.listings = self.fetch() or []
            if not result.listings:
                result.detail = "no matching listings returned"
        except Exception as e:
            result.status = "ERROR"
            result.detail = f"{type(e).__name__}: {e}"[:300]

        result.duration_s = time.time() - started
        return result

    def throttle(self):
        time.sleep(float(self.cfg["sources"].get("request_delay_seconds", 3.0)))
