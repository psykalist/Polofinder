# PoloFinder

Daily hunt for a **VW Polo, Match trim or above, 2021 facelift onward, 1.0 TSI 95PS,
under 30,000 miles, under £12,500**, excluding insurance write-offs. Emails you a
ranked report at 08:00 UK time every morning.

Searching from **GL53 0ES** (Cheltenham) — every car shows an estimated distance from home.

---

## Read this first: what actually gets scraped

I checked the `robots.txt` of every major UK car site on 2026-07-18. Most of them
explicitly disallow the filtered-search URLs a scraper needs:

| Site | What its robots.txt says |
|---|---|
| AutoTrader | Bot-protected, robots.txt unreachable to automated clients |
| Motors.co.uk | `Disallow: /car-*` — every vehicle detail page |
| CarGurus | `Disallow: /Cars/inventorylisting/`, `Disallow: /search?` |
| heycar | Disallows `price__gte`, `mileage__*`, `postcode`, `radius`; also blanket-blocks `ClaudeBot` |
| Arnold Clark | `Disallow: /used-cars/search?*`, `Disallow: /vehicles?*` |
| Gumtree | `Disallow: /*&*` — kills any multi-filter search |

So PoloFinder splits sites into two groups:

- **Scraped** — eBay (official Browse API), Gumtree (single-filter pages that
  robots.txt permits), PistonHeads. Real listings, fully parsed, scored and deduped.
- **Deep link** — everything else. The report gives you a pre-built, fully-filtered
  search URL you click once. No scraping, no ban risk, still one click away.

Both groups appear in the report's "Every site checked" table so you always see
the full picture and *why* a site returned nothing.

If you want to scrape the blocked sites anyway, set `sources.respect_robots: false`
in `config.yaml`. That's your call and your legal footing — and be aware GitHub
Actions runners use shared IP ranges that these sites fingerprint and block quickly.

---

## Setup

```bash
git clone <your-repo-url> && cd polofinder
pip install -r requirements.txt
playwright install chromium
python -m polofinder.run --no-email     # try it locally
```

### GitHub Actions (the 08:00 email)

Push this repo to GitHub, then add these under
**Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | a Gmail **App Password**, not your login password |
| `REPORT_TO` | where to send it |
| `EBAY_APP_ID` | optional, free from [dev.ebay.com](https://developer.ebay.com) |
| `EBAY_CERT_ID` | optional, pairs with the above |

> Gmail App Password: enable 2FA, then Google Account → Security → App passwords.
> Your normal password will not work over SMTP.

Without the eBay keys everything still runs — you just lose eBay's live results
and keep all the deep links.

The workflow is scheduled twice (07:00 and 08:00 UTC) and self-gates on UK local
time, so you get exactly one email at 08:00 whether it's GMT or BST.

---

## How cars are ranked

**EXACT MATCH** — Polo, 1.0 TSI 95PS, Match trim or above, 2021+, under 30k miles,
at or under £12,500, no write-off history.

**STRETCH BUDGET** — right car, slightly over: up to £14,000 or up to 35,000 miles.
Each card tells you exactly how far over it is.

**WORTH A LOOK** — not your spec but close: 110PS Polos, plus SEAT Ibiza,
Škoda Fabia and Audi A1 (same MQB A0 platform and 1.0 TSI engine), and 1.0 TSI Golfs.

Within each tier, cars sort by **extras score** then price. Rear camera carries the
heaviest weight since you flagged it — adjust any weight in `config.yaml`.

### Trim ladder

Post-2021 facelift the UK range is Polo → Life → **Match** → Style → R-Line → GTI.
Life sits *below* Match and is rejected. Pre-2021 cars are rejected from EXACT even
if badged Match, because pre-facelift Match is a different car
(set `min_year_strict: false` to demote them to WORTH A LOOK instead of dropping them).

### When the advert doesn't state 95PS

Most real listings just say "1.0 TSI Match" — the output lives in a spec table or
isn't given at all. Throwing those away would lose good cars, so PoloFinder keeps
them in **EXACT MATCH** and badges them **95PS UNCONFIRMED** for you to verify.
It reads power from spec tables and `cc` figures where it can, and any advert that
*explicitly* states 110PS (or 65/80/150) is never treated as unknown.

Change `target.power_unknown_policy` in `config.yaml`:
`include` (default) · `demote` to STRETCH · `exclude` entirely.

### Write-off filtering

Rejects Cat S, C, N and D. The regex is deliberately careful about the common false
positive — sellers writing "HPI clear, not a Cat S" or "unrecorded" should *not* be
filtered out, and there are tests covering exactly that.

**This is inferred from advert text and is not a substitute for a proper HPI check
before you pay for anything.** Plenty of write-offs simply aren't disclosed in the ad.

### Seller type

Every card is badged **PRIVATE SELLER** / **TRADE / DEALER** / **SELLER UNKNOWN**,
inferred from the seller name, ad wording, and which site it came from.

---

## Configuration

Everything lives in `config.yaml` — budget, mileage, trim floor, postcode, radius,
extras weights, which sources are on. No code changes needed.

## Repo layout

```
polofinder/
  models.py      Listing dataclass, parsers, plate-based fingerprinting
  matching.py    Tiering, write-off regex, trim ladder, extras scoring
  geo.py         postcodes.io geocoding, distance from GL53 0ES
  robots.py      robots.txt cache and checker
  browser.py     Playwright wrapper (cookie banners, UA, timeouts)
  dedupe.py      Cross-site dedupe, new-today flags, price-drop tracking
  report.py      HTML email + Markdown archive
  emailer.py     SMTP send
  run.py         Orchestrator
  sources/       One class per site
tests/           38 tests, focused on write-off and trim edge cases
```

## Useful commands

```bash
python -m polofinder.run                # full run + email
python -m polofinder.run --no-email     # writes reports/ only
python -m polofinder.run --dry-run      # no network, renders the shell
python -m pytest tests/ -q              # run the tests
```

Reports are archived to `reports/YYYY-MM-DD.html` and `.md`, so you build a price
history over time. Repeat listings are flagged with price drops when they fall.
