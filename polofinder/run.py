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
    ap.add_argument("--debug", action="store_true",
                    help="show why listings were rejected and what got parsed")
    ap.add_argument("--only", default=None,
                    help="run a single source, e.g. --only gumtree")
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
            if args.only and cls.key != args.only:
                continue
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

    if args.debug:
        _debug_dump(listings, rejected)

    if cfg["email"].get("enabled") and not args.no_email:
        new = len([l for l in matched if l.is_new])
        should, why = _should_email(matched, counts, cfg)
        if not should:
            print(f"[email] skipped - {why}")
            return 0
        subject = (f"{cfg['email']['subject_prefix']} {counts[TIER_ORDER[0]]} exact, "
                   f"{len(matched)} total, {new} new - {stamp}")
        if why == "heartbeat":
            subject = f"{cfg['email']['subject_prefix']} weekly check-in - {stamp}"
        try:
            send(html, subject, cfg)
            _record_send()
        except Exception as e:
            print(f"[email] FAILED: {e}", file=sys.stderr)
            return 1
    return 0


_LAST_SEND = os.path.join(os.path.dirname(__file__), "..", ".cache", "last_email.txt")


def _record_send():
    os.makedirs(os.path.dirname(_LAST_SEND), exist_ok=True)
    with open(_LAST_SEND, "w") as f:
        f.write(date.today().isoformat())


def _days_since_send():
    try:
        with open(_LAST_SEND) as f:
            last = date.fromisoformat(f.read().strip())
        return (date.today() - last).days
    except Exception:
        return 10**6


def _should_email(matched, counts, cfg):
    """Only interrupt Kieran when there's something worth interrupting for."""
    em = cfg.get("email", {})
    alert = em.get("alert_on", {}) or {}

    if alert.get("exact_match", True) and counts.get(TIER_ORDER[0]):
        return True, "exact match found"
    if alert.get("stretch_budget", True) and counts.get(TIER_ORDER[1]):
        return True, "stretch-budget match found"
    if alert.get("worth_a_look", False) and counts.get(TIER_ORDER[2]):
        return True, "near-miss found"
    if alert.get("price_drops", True) and any(l.price_drop for l in matched):
        return True, "price drop on a tracked car"

    hb = int(em.get("heartbeat_days", 0) or 0)
    if hb and _days_since_send() >= hb:
        return True, "heartbeat"

    if em.get("send_when_empty", False):
        return True, "send_when_empty is on"
    return False, "nothing worth emailing about"


def _debug_dump(listings, rejected):
    """Why did everything get thrown away? Usually a parser returning None."""
    from collections import Counter

    print("\n" + "=" * 72)
    print("REJECTION REASONS")
    print("=" * 72)
    for reason, n in Counter(l.reject_reason for l in rejected).most_common():
        print(f"  {n:4}  {reason}")

    print("\n" + "=" * 72)
    print("FIELD PARSE HEALTH  (None means the selector or regex missed)")
    print("=" * 72)
    fields = ["price", "mileage", "year", "trim", "power_ps", "location", "title"]
    total = len(listings) or 1
    for f in fields:
        got = sum(1 for l in listings if getattr(l, f, None) not in (None, "", 0))
        bar = "#" * int(20 * got / total)
        flag = "  <-- BROKEN" if got == 0 else ("  <-- patchy" if got < total * 0.5 else "")
        print(f"  {f:12} {got:3}/{total:3}  {bar:20}{flag}")

    print("\n" + "=" * 72)
    print("FIRST 5 PARSED LISTINGS (raw)")
    print("=" * 72)
    for l in listings[:5]:
        print(f"\n  source   : {l.source}")
        print(f"  title    : {(l.title or '')[:90]}")
        print(f"  price    : {l.price}")
        print(f"  mileage  : {l.mileage}")
        print(f"  year     : {l.year}")
        print(f"  trim     : {l.trim}")
        print(f"  power    : {l.power_ps}")
        print(f"  location : {l.location}")
        print(f"  url      : {(l.url or '')[:90]}")
        print(f"  rejected : {l.reject_reason}")
        print(f"  raw_spec : {(l.raw_spec or '')[:160]!r}")


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
