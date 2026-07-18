"""robots.txt awareness.

Every site we touch gets checked before we fetch. Sites that disallow the
search paths are recorded with a reason and surfaced in the report as
deep links instead of being silently dropped.
"""
from __future__ import annotations

import urllib.robotparser as urobot
from urllib.parse import urlparse
from typing import Dict, Optional

import requests


class RobotsCache:
    def __init__(self, user_agent: str, enabled: bool = True):
        self.user_agent = user_agent
        self.enabled = enabled
        self._parsers: Dict[str, Optional[urobot.RobotFileParser]] = {}

    def _parser(self, url: str) -> Optional[urobot.RobotFileParser]:
        base = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if base in self._parsers:
            return self._parsers[base]
        rp = urobot.RobotFileParser()
        try:
            r = requests.get(
                base + "/robots.txt",
                headers={"User-Agent": self.user_agent},
                timeout=15,
            )
            if r.ok:
                rp.parse(r.text.splitlines())
            else:
                rp = None
        except Exception:
            rp = None
        self._parsers[base] = rp
        return rp

    def allowed(self, url: str) -> bool:
        """True if we may fetch. Fails OPEN when robots.txt is unreachable."""
        if not self.enabled:
            return True
        rp = self._parser(url)
        if rp is None:
            return True
        # Check both our UA and the generic one; honour whichever is stricter.
        return rp.can_fetch(self.user_agent, url) and rp.can_fetch("*", url)
