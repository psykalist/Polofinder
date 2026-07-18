"""Orchestrator. `python -m polofinder.run`"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from . import config as config_mod
from . import dedupe, geo, report
from .browser import Browser
from .emailer import send
from .matching import classify, TIER_ORDER
from .robots import RobotsCache
from .sources import ALL_SOURCES
from .sources.base import SourceResult


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find a VW Polo.")
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="skip network scraping, just render the report shell")
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)
    enabled = cfg["sources"].get("enabled", {})
    robots = RobotsCache(cfg["sources"]["user_agent"],
                         cfg["sources"].get("respect_robots", True))

    results, listings = [], []
    needs_browser = any(
        enabled.get(S.key, True) and not S.deeplink_only for S in ALL_SOURCES
    ) and not args.dry_run

    browser_ctx = Browser(cfg) if needs_browser else _NullCtx()
    with browser_ctx as browser:
        for cls in ALL_SOURCES:
            if not enabled.get(cls.key, True):
                results.append(SourceResult(cls.key, cls.name, cls.homepage,
                                            "DISABLED", detail="disabled in config.yaml"))
                continue
            src = cls(cfg, robots, browser)
            if args.dry_run and not cls.deeplink_only:
                r = SourceResult(cls.key, cls.name, cls.homepage, "DISABLED",
                                 detail="dry run", search_url=_safe_url(src))
            else:
                r = src.run()
            results.append(r)
            listings.extend(r.listings)
            print(f"[{r.status:14}] {r.name:22} {r.count:3} listings  {r.detail[:60]}")

    # classify -> dedupe -> distance
    for l in listings:
        classify(l, cfg)
    matched = [l for l in listings if l.tier]
    rejected = [l for l in listings if l.reject_reason]
    matched = dedupe.cross_site_dupes(matched)
    dedupe.mark_new(matched)
    try:
        geo.annotate_distances(matched, cfg)
    except Exception as e:
        print(f"[geo] skipped: {e}")

    if cfg["report"].get("only_new"):
        matched = [l for l in matched if l.is_new or l.price_drop]

    html = report.build_html(matched, results, cfg, rejected)
    md = report.build_markdown(matched, results, cfg)

    os.makedirs("reports", exist_ok=True)
    stamp = date.today().isoformat()
    with open(f"reports/{stamp}.html", "w") as f:
        f.write(html)
    with open(f"reports/{stamp}.md", "w") as f:
        f.write(md)
    with open("reports/latest.html", "w") as f:
        f.write(html)

    counts = {t: len([l for l in matched if l.tier == t]) for t in TIER_ORDER}
    print("\n" + " | ".join(f"{t}: {c}" for t, c in counts.items()))
    print(f"Rejected {len(rejected)} (write-offs, over budget, wrong spec)")

    if cfg["email"].get("enabled") and not args.no_email:
        new = len([l for l in matched if l.is_new])
        subject = (f"{cfg['email']['subject_prefix']} {counts[TIER_ORDER[0]]} exact, "
                   f"{len(matched)} total, {new} new - {stamp}")
        try:
            send(html, subject, cfg)
        except Exception as e:
            print(f"[email] FAILED: {e}", file=sys.stderr)
            return 1
    return 0


class _NullCtx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def _safe_url(src):
    try:
        return src.search_url()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
