"""Spec matching, write-off exclusion, extras scoring, tier assignment."""
from __future__ import annotations

import re
from typing import Optional

from .models import Listing

TIER_EXACT = "EXACT MATCH"
TIER_STRETCH = "STRETCH BUDGET"
TIER_LOOK = "WORTH A LOOK"
TIER_ORDER = [TIER_EXACT, TIER_STRETCH, TIER_LOOK]

# VW Polo Mk6 facelift (2021->) UK range, low to high.
# Pre-facelift-only trims (S, SE, Beats, SEL) are kept so we can still rank
# and explain older cars that turn up, but min_year gates them out.
TRIM_RANK = {
    "s": 1,
    "se": 2,
    "beats": 3,          # pre-facelift, sat around SE/Match level
    "polo": 3,           # facelift entry trim is just "Polo"
    "life": 4,
    "match": 5,          # <- the floor you asked for
    "style": 6,
    "sel": 6,            # pre-facelift equivalent of Style
    "r-line": 7,
    "rline": 7,
    "gti": 8,
}

# Longest-first so "r-line" wins over "line", "sel" over "se".
_TRIM_PATTERNS = [
    ("r-line", r"\br[\s\-]?line\b"),
    ("gti",    r"\bgti\b"),
    ("match",  r"\bmatch\b"),
    ("style",  r"\bstyle\b"),
    ("beats",  r"\bbeats\b"),
    ("sel",    r"\bsel\b"),
    ("life",   r"\blife\b"),
    ("se",     r"\bse\b"),
    ("s",      r"\bs\b"),
]

# --- write-off / provenance -------------------------------------------------

def _writeoff_re(categories) -> re.Pattern:
    cats = "".join(c.upper() for c in categories)
    return re.compile(
        r"\bcat(?:egory)?[\s\-\.]*([" + cats + cats.lower() + r"])\b"
        r"|\b(?:insurance\s+)?(?:write[\s\-]?off|writeoff)\b"
        r"|\bsalvage\b"
        r"|\binsurance\s+loss\b"
        r"|\bdamage[d]?\s+repair(?:ed|able)?\b",
        re.I,
    )

# Phrases that LOOK like a write-off flag but are actually the seller saying
# the car is clean. These must not trigger a rejection.
_NEGATED = re.compile(
    r"\b(?:not|non|never|no)[\s\-]+(?:a\s+)?(?:cat\s*[scnd]\b|recorded|damaged|"
    r"write[\s\-]?off|writeoff|salvage)"
    r"|\bunrecorded\b"
    r"|\bhpi\s+clear\b"
    r"|\bclear\s+hpi\b"
    r"|\bno\s+accident"
    r"|\bnever\s+been\s+(?:in\s+)?an?\s+accident",
    re.I,
)


def writeoff_check(listing: Listing, categories) -> Optional[str]:
    """Return a rejection reason if this looks like a Cat S/C/N/D car."""
    text = listing.haystack
    if not text:
        return None
    # Blank out the reassuring phrases first, then look for real flags.
    scrubbed = _NEGATED.sub(" ", text)
    m = _writeoff_re(categories).search(scrubbed)
    if not m:
        return None
    if m.group(1):
        return f"Insurance write-off: Cat {m.group(1).upper()}"
    return f"Insurance write-off flagged ({m.group(0).strip()})"


# --- engine / power ---------------------------------------------------------

_POWER_RE = re.compile(r"\b(\d{2,3})\s*(?:ps|bhp|hp)\b", re.I)
# Sellers very often write "1.0 TSI 95" with no PS/bhp suffix at all.
_BARE_POWER_RE = re.compile(r"\b(?:tsi|tfsi|mpi|evo)\s*(\d{2,3})\b", re.I)
_LITRE_RE = re.compile(r"\b(\d)\.(\d)\s*(?:l\b|litre|tsi|tfsi|mpi|tdi)", re.I)


def infer_power_ps(listing: Listing) -> Optional[int]:
    if listing.power_ps:
        return listing.power_ps
    for regex in (_POWER_RE, _BARE_POWER_RE):
        m = regex.search(listing.haystack)
        if not m:
            continue
        val = int(m.group(1))
        # bhp -> PS is ~1.0139; 95PS shows up as 94/95bhp. Snap to known outputs.
        for known in (65, 80, 95, 110, 115, 150, 200, 207):
            if abs(val - known) <= 2:
                return known
        # A bare number that matches no known output is probably not power
        # at all (trim numbers, engine codes), so ignore it.
        if regex is _BARE_POWER_RE:
            continue
        return val
    return None


def infer_litres(listing: Listing) -> Optional[float]:
    if listing.engine_litres:
        return listing.engine_litres
    m = _LITRE_RE.search(listing.haystack)
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def is_turbo(listing: Listing) -> Optional[bool]:
    h = listing.haystack
    if re.search(r"\bts[ifg]\b|\btfsi\b|\bturbo\b", h):
        return True
    if re.search(r"\bmpi\b|\bevo\b.*\b(?:65|80)\s*ps", h):
        return False
    return None


def infer_trim(listing: Listing) -> Optional[str]:
    text = (listing.trim or "") + " " + (listing.title or "")
    text = text.lower()
    for name, pattern in _TRIM_PATTERNS:
        if re.search(pattern, text):
            return name
    return None


def trim_rank(trim: Optional[str]) -> Optional[int]:
    return TRIM_RANK.get((trim or "").lower().replace(" ", "")) or TRIM_RANK.get(
        (trim or "").lower()
    )


# --- extras -----------------------------------------------------------------

def score_extras(listing: Listing, extras_cfg: dict):
    """Return (score, [human-readable extras found])."""
    text = listing.haystack
    score, found = 0, []
    for key, cfg in (extras_cfg or {}).items():
        for pat in cfg.get("patterns", []):
            # \b around short tokens like "acc" and "dab" to avoid false hits
            if re.search(r"\b" + re.escape(pat) + r"\b", text):
                score += int(cfg.get("weight", 1))
                found.append(key.replace("_", " ").title())
                break
    return score, found


# --- main classifier --------------------------------------------------------

def classify(listing: Listing, cfg: dict) -> Listing:
    """Assign tier, score and reject_reason. Mutates and returns the listing."""
    t = cfg["target"]
    b = cfg["budget"]
    ex = cfg.get("exclusions", {})

    listing.power_ps = infer_power_ps(listing)
    listing.engine_litres = infer_litres(listing)
    listing.trim = infer_trim(listing) or listing.trim
    listing.seller_type = infer_seller_type(listing)

    # --- hard rejects --------------------------------------------------
    reason = writeoff_check(listing, ex.get("write_off_categories", ["S", "C"]))
    if reason:
        listing.reject_reason = reason
        return listing

    for kw in ex.get("exclude_keywords", []):
        if kw.lower() in listing.haystack:
            listing.reject_reason = f"Excluded keyword: {kw}"
            return listing

    max_owners = ex.get("max_owners")
    if max_owners and listing.owners and listing.owners > max_owners:
        listing.reject_reason = f"{listing.owners} owners (max {max_owners})"
        return listing

    if listing.price is None:
        listing.reject_reason = "No price listed (POA)"
        return listing

    if listing.price > b["stretch_price"]:
        listing.reject_reason = f"£{listing.price:,} over stretch budget"
        return listing

    # --- scoring -------------------------------------------------------
    listing.score, listing.extras_found = score_extras(listing, cfg.get("extras", {}))

    is_polo = (listing.model or "").strip().lower() == "polo"
    rank = trim_rank(listing.trim)
    min_rank = TRIM_RANK.get(str(t.get("min_trim", "match")).lower(), 5)
    turbo = is_turbo(listing)

    litres_ok = listing.engine_litres is None or abs(
        listing.engine_litres - t["engine_litres"]
    ) < 0.05
    tol = t.get("power_ps_tolerance", 0)
    power_ok = listing.power_ps is not None and abs(listing.power_ps - t["power_ps"]) <= tol
    trim_ok = rank is not None and rank >= min_rank
    year_ok = listing.year is not None and listing.year >= t.get("min_year", 0)

    within_budget = listing.price <= b["max_price"]
    within_miles = listing.mileage is not None and listing.mileage <= b["max_mileage"]
    within_stretch_miles = (
        listing.mileage is not None and listing.mileage <= b["stretch_mileage"]
    )

    # Explain-yourself notes so the report is readable at 8am.
    if listing.power_ps and listing.power_ps != t["power_ps"]:
        listing.notes.append(f"{listing.power_ps}PS, not {t['power_ps']}PS")
    if rank is not None and rank < min_rank:
        listing.notes.append(f"{(listing.trim or '?').title()} trim - below {t['min_trim']}")
    if listing.year and not year_ok:
        listing.notes.append(f"{listing.year} - pre-{t.get('min_year')} facelift")
    if turbo is False:
        listing.notes.append("Non-turbo MPI engine")

    # --- tier ----------------------------------------------------------
    if (
        is_polo and litres_ok and power_ok and trim_ok and year_ok
        and turbo is not False and within_budget and within_miles
    ):
        listing.tier = TIER_EXACT
        return listing

    strict_year = t.get("min_year_strict", True)
    if (
        is_polo and litres_ok and power_ok and trim_ok
        and (year_ok or not strict_year)
        and turbo is not False
        and listing.price <= b["stretch_price"] and within_stretch_miles
    ):
        listing.tier = TIER_STRETCH
        if not within_budget:
            listing.notes.append(f"£{listing.price - b['max_price']:,} over budget")
        if not within_miles and listing.mileage:
            listing.notes.append(f"{listing.mileage:,} miles - over 30k")
        return listing

    if _is_alternative(listing, cfg) and within_stretch_miles:
        listing.tier = TIER_LOOK
        return listing

    listing.reject_reason = "Does not match spec"
    return listing


def _is_alternative(listing: Listing, cfg: dict) -> bool:
    """Close-enough cars: a 110PS Polo, or a platform sibling."""
    make = (listing.make or "").lower()
    model = (listing.model or "").lower()
    for alt in cfg.get("alternatives", []):
        if alt["make"].lower() == make and alt["model"].lower() == model:
            # Siblings still have to be a sensible engine, not a 1.6 diesel.
            if listing.engine_litres and listing.engine_litres > 1.6:
                continue
            listing.notes.append(alt.get("note", ""))
            return True
    return False


def sort_key(listing: Listing):
    """Best fit first: tier, then extras score desc, then price asc."""
    tier_idx = TIER_ORDER.index(listing.tier) if listing.tier in TIER_ORDER else 99
    return (tier_idx, -listing.score, listing.price or 10**9)


# --- seller type ------------------------------------------------------------

_DEALER_HINTS = re.compile(
    r"\b(?:ltd|limited|plc|motors?\b|autos?\b|car\s+sales|dealership|garage|"
    r"trade|showroom|approved|warranty\s+included|part\s+exchange|px\s+welcome|"
    r"finance\s+available|hpi\s+clear|group\b|centre\b|center\b|specialists?)\b",
    re.I,
)
_PRIVATE_HINTS = re.compile(
    r"\b(?:private\s+sale|private\s+seller|selling\s+my|my\s+car|reluctant\s+sale|"
    r"first\s+car|no\s+dealers|no\s+traders|genuine\s+reason\s+for\s+sale)\b",
    re.I,
)


def infer_seller_type(listing: Listing) -> str:
    """'Dealer' | 'Private' | 'Unknown'. Explicit field wins over guessing."""
    explicit = (listing.seller_type or "").strip().lower()
    if explicit in ("dealer", "trade", "commercial", "business"):
        return "Dealer"
    if explicit in ("private", "owner", "individual"):
        return "Private"

    text = " ".join(filter(None, [listing.seller, listing.title, listing.description]))
    if _PRIVATE_HINTS.search(text):
        return "Private"
    if _DEALER_HINTS.search(text):
        return "Dealer"
    # Dealer-group sites only ever list trade stock.
    if listing.source in {
        "arnoldclark", "evanshalshaw", "bigmotoringworld", "thecarpeople",
        "cinch", "heycar", "carwow", "motors",
    }:
        return "Dealer"
    return "Unknown"
