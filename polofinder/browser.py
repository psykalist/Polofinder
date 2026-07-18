"""Thin Playwright wrapper shared by the scraping adapters."""
from __future__ import annotations


class Browser:
    def __init__(self, cfg: dict):
        self.cfg = cfg["sources"]
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.cfg.get("headless", True),
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._context = self._browser.new_context(
            user_agent=self.cfg.get("user_agent"),
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
            timezone_id="Europe/London",
        )
        self._context.set_default_timeout(self.cfg.get("timeout_seconds", 45) * 1000)
        return self

    def __exit__(self, *exc):
        for closer in (self._context, self._browser):
            try:
                closer and closer.close()
            except Exception:
                pass
        try:
            self._pw and self._pw.stop()
        except Exception:
            pass

    def open(self, url: str):
        page = self._context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        _dismiss_cookies(page)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        return page


_COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Allow all')",
    "[data-testid='cookie-accept-all']",
    "button[aria-label*='Accept']",
]


def _dismiss_cookies(page):
    for sel in _COOKIE_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=3000)
                page.wait_for_timeout(600)
                return
        except Exception:
            continue
