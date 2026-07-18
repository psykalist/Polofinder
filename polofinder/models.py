"""Normalised listing model. Every source adapter must emit these."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    source: str                       # e.g. "ebay", "autotrader"
    url: str
    title: str
    price: Optional[int] = None       # GBP, integer pounds
    mileage: Optional[int] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    engine_litres: Optional[float] = None
    power_ps: Optional[int] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None
    body: Optional[str] = None
    doors: Optional[int] = None
    owners: Optional[int] = None
    location: Optional[str] = None
    seller: Optional[str] = None
    seller_type: Optional[str] = None   # "dealer" | "private"
    image: Optional[str] = None
    description: str = ""
    raw_spec: str = ""                  # any extra spec/feature text scraped
    distance_miles: Optional[int] = None  # road-miles estimate from home postcode

    # populated by matching.py
    tier: Optional[str] = None
    score: int = 0
    extras_found: list = field(default_factory=list)
    reject_reason: Optional[str] = None
    notes: list = field(default_factory=list)
    is_new: bool = True
    first_seen: Optional[str] = None
    price_drop: Optional[int] = None
    power_unconfirmed: bool = False   # advert never stated PS; needs checking
    also_on: list = field(default_factory=list)   # [(source, url)] same car elsewhere

    @property
    def haystack(self) -> str:
        """All free text, lowercased - what the feature/write-off regexes run against."""
        return " ".join(
            filter(None, [self.title, self.description, self.raw_spec, self.trim])
        ).lower()

    @property
    def fingerprint(self) -> str:
        """Stable ID for dedupe across days and across sites.

        Prefers a registration plate if one appears in the text, since the same
        car is very often listed on five sites at once with different ad IDs.
        """
        plate = extract_plate(self.haystack)
        if plate:
            return "plate:" + plate
        basis = f"{self.make}|{self.model}|{self.year}|{self.mileage}|{self.price}"
        if None in (self.year, self.mileage, self.price):
            basis = self.url          # not enough signal, fall back to URL identity
        return "hash:" + hashlib.sha1(basis.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)


# UK current-style plate: two letters, two digits, three letters (e.g. AB21 CDE)
PLATE_RE = re.compile(r"\b([a-z]{2}\d{2}\s?[a-z]{3})\b")

_PLATE_FALSE_POSITIVES = {"cat", "vat", "mot", "bhp"}


def extract_plate(text: str) -> Optional[str]:
    for m in PLATE_RE.finditer(text or ""):
        candidate = m.group(1).replace(" ", "").upper()
        if candidate[:3].lower() in _PLATE_FALSE_POSITIVES:
            continue
        return candidate
    return None


def parse_price(text) -> Optional[int]:
    """'£12,495' / '12495.00' / 12495 -> 12495. Returns None for POA."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    t = str(text).lower().replace(",", "")
    if any(w in t for w in ("poa", "price on application", "call")):
        return None
    m = re.search(r"(\d[\d.]*)", t)
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except ValueError:
        return None


def parse_mileage(text) -> Optional[int]:
    """'28,450 miles' / '28k miles' / 28450 -> 28450."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    t = str(text).lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*k\b", t)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r"(\d+)", t)
    return int(m.group(1)) if m else None


def parse_year(text) -> Optional[int]:
    if text is None:
        return None
    if isinstance(text, int):
        return text if 1990 < text < 2100 else None
    m = re.search(r"\b(19[89]\d|20[0-4]\d)\b", str(text))
    return int(m.group(1)) if m else None
