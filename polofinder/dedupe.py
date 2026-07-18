"""Tracks what we've already emailed, so 'new today' actually means new."""
from __future__ import annotations

import json
import os
from datetime import date

STORE = os.path.join(os.path.dirname(__file__), "..", ".cache", "seen.json")


def load() -> dict:
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return {}


def save(store: dict) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w") as f:
        json.dump(store, f, indent=1)


def mark_new(listings) -> None:
    """Set .is_new and record first-seen date + price history."""
    store = load()
    today = date.today().isoformat()
    for l in listings:
        fp = l.fingerprint
        rec = store.get(fp)
        if rec is None:
            l.is_new = True
            store[fp] = {"first_seen": today, "url": l.url,
                         "prices": [[today, l.price]]}
        else:
            l.is_new = False
            l.first_seen = rec.get("first_seen")
            prices = rec.setdefault("prices", [])
            if not prices or prices[-1][1] != l.price:
                prices.append([today, l.price])
                if len(prices) > 1 and prices[-2][1] and l.price:
                    delta = l.price - prices[-2][1]
                    if delta < 0:
                        l.price_drop = abs(delta)
                        l.notes.append(f"Price dropped £{abs(delta):,}")
    save(store)


def cross_site_dupes(listings) -> list:
    """Collapse the same car listed on several sites into one entry."""
    by_fp = {}
    for l in listings:
        fp = l.fingerprint
        if fp in by_fp:
            by_fp[fp].also_on.append((l.source, l.url))
        else:
            l.also_on = []
            by_fp[fp] = l
    return list(by_fp.values())
