"""Every UK site PoloFinder looks at.

Each class declares whether it can be scraped compliantly. The ones marked
deeplink_only had their filtered-search paths checked against robots.txt on
2026-07-18 and found to be Disallowed - so we build you a one-click search
URL instead of scraping them.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode, quote

from ..models import Listing, parse_price, parse_mileage, parse_year
from .base import Source


def _pc(cfg) -> str:
    return (cfg.get("location", {}).get("postcode") or "").replace(" ", "")


def _radius(cfg) -> int:
    return int(cfg.get("location", {}).get("radius_miles", 200))


# =============================================================================
#  SCRAPEABLE / API SOURCES
# =============================================================================

class EbaySource(Source):
    """eBay Browse API - official, free, structured. The best source here.

    Needs EBAY_APP_ID + EBAY_CERT_ID as env vars (free dev.ebay.com account).
    Falls back to a deep link if credentials are absent.
    """
    key = "ebay"
    name = "eBay Motors UK"
    homepage = "https://www.ebay.co.uk/b/Cars/9801"
    api_based = True   # uses the Browse API, not the /sch/ pages robots.txt covers

    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    def search_url(self) -> str:
        q = urlencode({"_nkw": "volkswagen polo 1.0 tsi match", "_udhi": self.cfg["budget"]["stretch_price"]})
        return f"https://www.ebay.co.uk/sch/i.html?{q}"

    def _token(self):
        import os, base64, requests
        app_id, cert_id = os.getenv("EBAY_APP_ID"), os.getenv("EBAY_CERT_ID")
        if not (app_id and cert_id):
            return None
        basic = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
        r = requests.post(
            self.TOKEN_URL,
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials",
                  "scope": "https://api.ebay.com/oauth/api_scope"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def fetch(self):
        import requests
        token = self._token()
        if not token:
            raise RuntimeError(
                "EBAY_APP_ID / EBAY_CERT_ID not set - add them as GitHub secrets "
                "to enable live eBay results (free at dev.ebay.com)"
            )
        out = []
        for query in ("volkswagen polo 1.0 tsi", "vw polo match tsi"):
            r = requests.get(
                self.SEARCH_URL,
                headers={"Authorization": f"Bearer {token}",
                         "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"},
                params={
                    "q": query,
                    "category_ids": "9801",
                    "filter": f"price:[..{self.cfg['budget']['stretch_price']}],priceCurrency:GBP",
                    "limit": 100,
                },
                timeout=45,
            )
            if not r.ok:
                continue
            for item in r.json().get("itemSummaries", []) or []:
                specs = {a.get("name", "").lower(): a.get("value", "")
                         for a in item.get("localizedAspects", []) or []}
                out.append(Listing(
                    source=self.key,
                    url=item.get("itemWebUrl", ""),
                    title=item.get("title", ""),
                    price=parse_price((item.get("price") or {}).get("value")),
                    mileage=parse_mileage(specs.get("mileage")),
                    year=parse_year(specs.get("year") or item.get("title")),
                    make=specs.get("make") or "Volkswagen",
                    model=specs.get("model") or "Polo",
                    fuel=specs.get("fuel"),
                    transmission=specs.get("transmission"),
                    location=(item.get("itemLocation") or {}).get("postalCode")
                             or (item.get("itemLocation") or {}).get("city"),
                    seller=(item.get("seller") or {}).get("username"),
                    image=(item.get("image") or {}).get("imageUrl"),
                    description=item.get("shortDescription", "") or "",
                    raw_spec=" ".join(f"{k} {v}" for k, v in specs.items()),
                ))
            self.throttle()
        return _dedupe(out)


class GumtreeSource(Source):
    """Gumtree allows single-filter category pages; multi-param URLs are
    Disallowed (`Disallow: /*&*`). We use one allowed filter and post-filter
    the rest ourselves, which stays inside robots.txt."""
    key = "gumtree"
    name = "Gumtree"
    homepage = "https://www.gumtree.com/cars-vans-motorbikes/uk"

    def search_url(self) -> str:
        # Single query param only - robots.txt allows `?vehicle_mileage=` alone.
        return "https://www.gumtree.com/cars/uk/volkswagen+polo?vehicle_mileage=up_to_30000"

    def fetch(self):
        page = self.browser.open(self.search_url())
        cards = page.query_selector_all("article[data-q='search-result'], article.listing-maxi")
        out = []
        for c in cards:
            def txt(sel):
                el = c.query_selector(sel)
                return el.inner_text().strip() if el else ""
            href = ""
            a = c.query_selector("a[href]")
            if a:
                href = a.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.gumtree.com" + href
            title = txt("[data-q='tile-title'], h2")
            if not title:
                continue
            # Read each attribute element separately. Taking inner_text of the
            # container concatenates them with no separator, so the year runs
            # into the mileage: "2017" + "4,560 miles" -> "20174,560 miles".
            parts = []
            for el in c.query_selector_all(
                "[data-q='tile-attributes'] > *, .listing-attributes > *"
            ):
                try:
                    v = el.inner_text().strip()
                except Exception:
                    continue
                if v:
                    parts.append(v)
            attrs = " | ".join(parts) or txt(
                "[data-q='tile-attributes'], .listing-attributes"
            )
            out.append(Listing(
                source=self.key, url=href, title=title,
                price=parse_price(txt("[data-q='tile-price'], .listing-price")),
                mileage=parse_mileage(attrs, year=parse_year(title)),
                year=parse_year(title) or parse_year(attrs),
                make="Volkswagen", model="Polo",
                location=txt("[data-q='tile-location'], .listing-location"),
                seller_type=("private" if re.search(r"\bprivate\b", attrs, re.I)
                             else "dealer" if re.search(r"\btrade\b", attrs, re.I)
                             else None),
                description=txt("[data-q='tile-description'], .listing-description"),
                raw_spec=attrs,
            ))
        # Throttle between page fetches, never between cards already in memory.
        self.throttle()
        return out


class PistonHeadsSource(Source):
    key = "pistonheads"
    name = "PistonHeads"
    homepage = "https://www.pistonheads.com/classifieds"

    def search_url(self) -> str:
        # Path-based form; the ?Category=... query string is Disallowed.
        return "https://www.pistonheads.com/classifieds/used-cars/volkswagen/polo"

    def fetch(self):
        page = self.browser.open(self.search_url())
        out = []
        for c in page.query_selector_all("[data-testid='listing-card'], .listing-item"):
            a = c.query_selector("a[href]")
            href = a.get_attribute("href") if a else ""
            if href and href.startswith("/"):
                href = "https://www.pistonheads.com" + href
            body = c.inner_text()
            title = (c.query_selector("h2, h3").inner_text().strip()
                     if c.query_selector("h2, h3") else "")
            if not title:
                continue
            out.append(Listing(
                source=self.key, url=href, title=title,
                price=parse_price(_grab(body, r"£([\d,]+)")),
                mileage=parse_mileage(_grab(body, r"([\d,]+)\s*miles")),
                year=parse_year(title), make="Volkswagen", model="Polo",
                raw_spec=body,
            ))
        return out


# =============================================================================
#  DEEP-LINK-ONLY SOURCES
#  robots.txt checked 2026-07-18 - filtered search paths are Disallowed.
# =============================================================================

class AutoTraderSource(Source):
    key = "autotrader"
    name = "AutoTrader"
    homepage = "https://www.autotrader.co.uk"
    deeplink_only = True
    robots_note = ("Bot-protected (Cloudflare/Akamai); robots.txt unreachable to "
                   "automated clients. Largest UK inventory - worth the manual click.")

    def search_url(self) -> str:
        p = {
            "postcode": _pc(self.cfg), "radius": _radius(self.cfg),
            "make": "VOLKSWAGEN", "model": "POLO",
            "price-to": self.cfg["budget"]["stretch_price"],
            "maximum-mileage": self.cfg["budget"]["stretch_mileage"],
            "year-from": self.cfg["target"].get("min_year", 2021),
            "aggregatedTrim": "Match", "quantity-of-doors": 5,
            "fuel-type": "Petrol", "exclude-writeoff-categories": "on",
            "sort": "price-asc",
        }
        return "https://www.autotrader.co.uk/car-search?" + urlencode(p)


class MotorsSource(Source):
    """Motors.co.uk (trading as Cazoo).

    Selectors verified against live markup on 2026-07-18:
      card      .result-card
      make      h3                          "Volkswagen, Polo"
      variant   h4                          "2021 (21) - 1.0 TSI Match Euro 6 5-door"
      price     .result-card__vehicle-details   contains "Low Mileage£13,900"
      mileage   [class*="vehicle-info__mile"]   "22.2k"
      seller    [class*="dealer"]           "Mon Motors VW Gloucester01452 227271 *"
      distance  [class*="distance"]         "9 miles away"
      link      a[href^="/car-"]

    Note: Motors discards query-string filters and redirects to a bare
    /search/car/. Results come back sorted by distance from the saved
    postcode, which suits us - nearest first - but everything else has to be
    filtered client-side.
    """
    key = "motors"
    name = "Motors.co.uk"
    homepage = "https://www.motors.co.uk"
    deeplink_only = True
    local_capable = True
    robots_note = "robots.txt: `Disallow: /car-*` blocks all vehicle detail pages, plus `Disallow: /*?page=`"

    def search_url(self) -> str:
        # Filters are dropped by the site, but keep them for the human link.
        p = {"make": "Volkswagen", "model": "Polo",
             "postcode": _pc(self.cfg), "distance": _radius(self.cfg),
             "PriceTo": self.cfg["budget"]["stretch_price"],
             "MileageTo": self.cfg["budget"]["stretch_mileage"],
             "YearFrom": self.cfg["target"].get("min_year", 2021)}
        return "https://www.motors.co.uk/search/car/?" + urlencode(p)

    def fetch(self):
        page = self.browser.open(self.search_url())
        out = []
        for card in page.query_selector_all(".result-card"):
            def txt(sel):
                el = card.query_selector(sel)
                return el.inner_text().strip() if el else ""

            href = ""
            a = card.query_selector('a[href^="/car-"]')
            if a:
                href = a.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.motors.co.uk" + href.split("?")[0]

            make_model = txt("h3")           # "Volkswagen, Polo"
            variant = txt("h4")              # "2021 (21) - 1.0 TSI Match Euro 6 5-door"
            if not variant:
                continue

            details = txt(".result-card__vehicle-details")
            seller = txt('[class*="dealer"], [class*="seller"]')
            distance = txt('[class*="distance"], [class*="location"]')

            # Mileage renders as "22.2k" in its own element.
            miles_raw = txt('[class*="vehicle-info__mile"]')
            mileage = parse_mileage(miles_raw + " miles") if miles_raw else None

            dist_m = re.search(r"([\d.]+)\s*miles?\s*away", distance, re.I)

            listing = Listing(
                source=self.key, url=href,
                title=f"{make_model} {variant}".strip(),
                price=parse_price(_grab(details, r"£([\d,]+)")),
                mileage=mileage,
                year=parse_year(variant),
                make="Volkswagen", model="Polo",
                location=seller.split("0")[0].strip() or None,
                seller=seller,
                seller_type="dealer",     # Motors is trade stock only
                raw_spec=" | ".join(filter(None, [variant, details, distance])),
            )
            if dist_m:
                listing.distance_miles = int(round(float(dist_m.group(1))))
            out.append(listing)

        self.throttle()
        return out


class CarGurusSource(Source):
    key = "cargurus"
    name = "CarGurus UK"
    homepage = "https://www.cargurus.co.uk"
    deeplink_only = True
    local_capable = True
    robots_note = "robots.txt: `Disallow: /Cars/inventorylisting/` and `Disallow: /search?`"

    def search_url(self) -> str:
        p = {"sourceContext": "untrackedExternal", "zip": _pc(self.cfg),
             "distance": _radius(self.cfg), "entitySelectingHelper.selectedEntity": "d842",
             "maxPrice": self.cfg["budget"]["stretch_price"]}
        return "https://www.cargurus.co.uk/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?" + urlencode(p)


class HeycarSource(Source):
    key = "heycar"
    name = "heycar"
    homepage = "https://heycar.com/uk"
    deeplink_only = True
    robots_note = ("robots.txt disallows `price__gte`, `mileage__*`, `postcode`, `radius` "
                   "AND names ClaudeBot under a blanket `Disallow: /`")

    def search_url(self) -> str:
        return ("https://heycar.com/uk/volkswagen/polo?"
                + urlencode({"price__lte": self.cfg["budget"]["stretch_price"],
                             "mileage__lte": self.cfg["budget"]["stretch_mileage"],
                             "postcode": _pc(self.cfg), "radius": _radius(self.cfg)}))


class CinchSource(Source):
    key = "cinch"
    name = "cinch"
    homepage = "https://www.cinch.co.uk"
    deeplink_only = True
    local_capable = True
    robots_note = "SPA behind an internal JSON API; search params disallowed"

    def search_url(self) -> str:
        return ("https://www.cinch.co.uk/used-cars/volkswagen/polo?"
                + urlencode({"maxprice": self.cfg["budget"]["stretch_price"],
                             "maxmileage": self.cfg["budget"]["stretch_mileage"]}))


class CarwowSource(Source):
    key = "carwow"
    name = "carwow (used)"
    homepage = "https://www.carwow.co.uk/used-cars"
    deeplink_only = True
    robots_note = ("SPA; /used-cars/<make>/<model> 404s - verified 2026-07-18. "
                   "Landing page only, filter from there.")

    def search_url(self) -> str:
        # /used-cars/volkswagen/polo returns carwow's "wrong way" 404 page,
        # so link to the working landing page rather than a dead URL.
        return "https://www.carwow.co.uk/used-cars"


class ArnoldClarkSource(Source):
    key = "arnoldclark"
    name = "Arnold Clark"
    homepage = "https://www.arnoldclark.com"
    deeplink_only = True
    local_capable = True
    robots_note = "robots.txt: `Disallow: /used-cars/search?*` and `Disallow: /vehicles?*`"

    def search_url(self) -> str:
        return ("https://www.arnoldclark.com/used-cars/volkswagen/polo?"
                + urlencode({"price_to": self.cfg["budget"]["stretch_price"],
                             "mileage_to": self.cfg["budget"]["stretch_mileage"],
                             "postcode": _pc(self.cfg)}))


class EvansHalshawSource(Source):
    key = "evanshalshaw"
    name = "Evans Halshaw"
    homepage = "https://www.evanshalshaw.com"
    deeplink_only = True
    local_capable = True
    robots_note = "Dealer group site; faceted search paths disallowed"

    def search_url(self) -> str:
        return ("https://www.evanshalshaw.com/used-cars/volkswagen/polo/?"
                + urlencode({"maxprice": self.cfg["budget"]["stretch_price"],
                             "maxmileage": self.cfg["budget"]["stretch_mileage"]}))


class BigMotoringWorldSource(Source):
    key = "bigmotoringworld"
    name = "Big Motoring World"
    homepage = "https://www.bigmotoringworld.co.uk"
    deeplink_only = True
    local_capable = True
    robots_note = "Faceted search disallowed"

    def search_url(self) -> str:
        return ("https://www.bigmotoringworld.co.uk/used-cars/volkswagen/polo?"
                + urlencode({"price_max": self.cfg["budget"]["stretch_price"]}))


class TheCarPeopleSource(Source):
    key = "thecarpeople"
    name = "The Car People"
    homepage = "https://www.thecarpeople.co.uk"
    deeplink_only = True
    local_capable = True
    robots_note = "Faceted search disallowed"

    def search_url(self) -> str:
        return ("https://www.thecarpeople.co.uk/used-cars/volkswagen/polo/?"
                + urlencode({"maxPrice": self.cfg["budget"]["stretch_price"]}))


# =============================================================================

ALL_SOURCES = [
    EbaySource, GumtreeSource, PistonHeadsSource,
    AutoTraderSource, MotorsSource, CarGurusSource, HeycarSource,
    CinchSource, CarwowSource, ArnoldClarkSource, EvansHalshawSource,
    BigMotoringWorldSource, TheCarPeopleSource,
]


def _grab(text, pattern):
    m = re.search(pattern, text or "", re.I)
    return m.group(1) if m else None


def _dedupe(listings):
    seen, out = set(), []
    for l in listings:
        if l.url in seen:
            continue
        seen.add(l.url)
        out.append(l)
    return out
