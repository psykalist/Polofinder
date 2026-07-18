"""Standalone Gumtree selector diagnostic.

Run:  python diagnose_gumtree.py
Opens the search page, reports which selectors match, and saves the HTML so
the adapter can be fixed against what Gumtree actually serves today.
"""
import sys, yaml
from polofinder.browser import Browser
from polofinder.sources.sites import GumtreeSource

cfg = yaml.safe_load(open("config.yaml"))
# Headless unless you ask to watch it.
cfg["sources"]["headless"] = "--show" not in sys.argv

with Browser(cfg) as b:
    src = GumtreeSource(cfg, None, b)
    url = src.search_url()
    print(f"Opening: {url}\n")
    page = b.open(url)
    print(f"Title: {page.title()}\n")

    print("=" * 70)
    print("CARD SELECTORS")
    print("=" * 70)
    for sel in ["article[data-q='search-result']", "article.listing-maxi",
                "article", "[data-q='search-result']", "a[href*='/p/']",
                "[data-testid*='listing']", ".listing-link"]:
        try:
            print(f"  {len(page.query_selector_all(sel)):4}  {sel}")
        except Exception as e:
            print(f"   ERR  {sel}  {e}")

    cards = (page.query_selector_all("article[data-q='search-result']")
             or page.query_selector_all("article"))
    print(f"\nUsing {len(cards)} cards\n")

    if cards:
        print("=" * 70)
        print("FIELD SELECTORS (on first card)")
        print("=" * 70)
        c = cards[0]
        for sel in ["[data-q='tile-title']", "h2", "h3",
                    "[data-q='tile-price']", ".listing-price", "[class*='price']",
                    "[data-q='tile-attributes']", ".listing-attributes",
                    "[data-q='tile-location']", "[class*='location']",
                    "[data-q='tile-description']"]:
            el = c.query_selector(sel)
            val = el.inner_text().strip().replace("\n", " ")[:60] if el else None
            print(f"  {'OK ' if el else '-- '} {sel:34} {val}")

        print("\n" + "=" * 70)
        print("FIRST CARD FULL TEXT")
        print("=" * 70)
        print(c.inner_text()[:900])

        with open("gumtree_card.html", "w", encoding="utf-8") as f:
            f.write(c.inner_html())
        print("\nSaved first card HTML -> gumtree_card.html")

    with open("gumtree_page.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("Saved full page      -> gumtree_page.html")
    # Non-interactive by default so it can't look like a hang. Pass --wait to
    # keep the browser open for inspection.
    if "--wait" in sys.argv:
        input("\nPress Enter to close the browser...")
    else:
        print("\nDone. Re-run with --wait to keep the browser open.")
