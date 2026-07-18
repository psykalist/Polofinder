"""UK postcode geocoding + distance from home.

Uses postcodes.io - free, no API key, no rate limit worth worrying about.
Results are cached to disk so we geocode each town/postcode once, ever.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Optional, Tuple

import requests

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", ".cache", "geo.json")
API = "https://api.postcodes.io"

# Full postcode, or just the outward code (GL53, M1, SW1A)
_FULL_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
_OUT_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\b(?!\s*\d[A-Z]{2})", re.I)


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f)


_CACHE = _load_cache()


def geocode(place: str) -> Optional[Tuple[float, float]]:
    """Postcode, outward code, or town name -> (lat, lon). None if not found."""
    if not place:
        return None
    key = place.strip().lower()
    if key in _CACHE:
        v = _CACHE[key]
        return tuple(v) if v else None

    result = None
    try:
        m = _FULL_RE.search(place)
        if m:
            r = requests.get(f"{API}/postcodes/{m.group(1).replace(' ', '')}", timeout=15)
            if r.ok and r.json().get("result"):
                d = r.json()["result"]
                result = (d["latitude"], d["longitude"])

        if result is None:
            m = _OUT_RE.search(place)
            if m:
                r = requests.get(f"{API}/outcodes/{m.group(1)}", timeout=15)
                if r.ok and r.json().get("result"):
                    d = r.json()["result"]
                    result = (d["latitude"], d["longitude"])

        if result is None:
            # Fall back to treating it as a place name
            r = requests.get(f"{API}/places", params={"q": place, "limit": 1}, timeout=15)
            if r.ok and r.json().get("result"):
                d = r.json()["result"][0]
                result = (d["latitude"], d["longitude"])
        time.sleep(0.15)
    except Exception:
        result = None

    _CACHE[key] = list(result) if result else None
    _save_cache(_CACHE)
    return result


def haversine_miles(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def road_estimate(straight_miles: float) -> int:
    """Straight-line -> rough road miles. UK road factor is ~1.2-1.3x."""
    return int(round(straight_miles * 1.25))


def annotate_distances(listings, cfg) -> None:
    """Set .distance_miles on each listing, in place."""
    loc = cfg.get("location", {})
    if not loc.get("show_distance", True) or not loc.get("postcode"):
        return
    home = geocode(loc["postcode"])
    if not home:
        return
    comfortable = loc.get("comfortable_drive_miles", 75)
    for l in listings:
        coords = geocode(l.location or "")
        if not coords:
            continue
        miles = road_estimate(haversine_miles(home, coords))
        l.distance_miles = miles
        if miles > comfortable:
            l.notes.append(f"~{miles} mi away - long trip")
