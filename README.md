# PoloFinder

Daily hunt for a **VW Polo, Match trim or above, 2021 facelift onward, 1.0 TSI 95PS,
under 30,000 miles, under £14,000**, excluding insurance write-offs. Emails you a
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

Run these **one line at a time** (the comments below are notes, not commands):

```bash
git clone https://github.com/psykalist/Polofinder.git
cd Polofinder
pip install -r requirements.txt
python -m playwright install chromium
python -m polofinder.run --no-email
```

Use `python -m playwright`, not bare `playwright` — on Windows the script
directory often isn't on `PATH`, which gives `playwright: command not found`.

### Troubleshooting

**`Microsoft Visual C++ 14.0 or greater is required`** — pip is trying to compile
`greenlet` from source because no wheel matches your Python version. Requirements
use version ranges to avoid this; if you still hit it, either upgrade pip
(`python -m pip install --upgrade pip`) or use Python 3.12.

**`ModuleNotFoundError: No module named 'yaml'`** — the `pip install` above failed
part-way. Fix that first; nothing installed after the failure point.

**Git Bash vs cmd** — `cd /d D:\path` is cmd syntax. In Git Bash/MINGW64 use
`cd /d/claude/projects/polofinder`.

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
at or under £14,000, no write-off history.

**STRETCH BUDGET** — right car, slightly over: up to £16,000 or up to 35,000 miles.
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

## Self-hosted runner (local scraping)

Cloud CI runners share IP ranges these sites fingerprint and block. Your home
connection doesn't have that problem — which is why Motors and AutoTrader
render fine in your own browser but time out from GitHub's runners.

`.github/workflows/self-hosted.yml` runs the same job on your machine with
`sources.local_mode` enabled, which scrapes sites that are deep-link-only in
the cloud.

**Be clear about what that means.** Sites marked `local_capable` have
robots.txt rules disallowing their search paths; local mode fetches them
anyway. That's an opt-in decision, made at personal scale for one car search.
**AutoTrader is deliberately excluded** — its Terms of Use prohibit automated
extraction regardless of where the request comes from, and its own
saved-search email alert does the same job with their blessing. Set that up
instead; it's better anyway (instant, no maintenance, no block risk).

### Setting up the runner

1. On GitHub: **Settings → Actions → Runners → New self-hosted runner**,
   pick Windows, and follow the download/configure commands it gives you.
2. Run it as a service so it survives reboots — the configure script offers
   this, answer `Y`.
3. Your machine must be awake at 08:00. Check
   **Settings → System → Power → Sleep**.
4. Optionally point it at a real Chrome profile so cookies and consent state
   persist and it looks less like automation:

   ```
   POLOFINDER_CHROME_PROFILE=C:\Users\kiera\polofinder-chrome
   ```

   Use a *dedicated* profile directory, not your day-to-day Chrome profile —
   Playwright needs exclusive access and will fail if Chrome is already
   running with it.

5. Disable the cloud workflow (`daily.yml`) if you don't want two emails.

### Simpler alternative

If a self-hosted runner feels like overkill, Windows Task Scheduler does the
same job with less setup: run `python -m polofinder.run` daily at 08:00 with
`POLOFINDER_LOCAL_MODE=1` set. You lose the Actions run history and artifacts,
but there's no runner service to maintain.

### Which sites work locally

| Site | Local | Note |
|---|---|---|
| Motors.co.uk | yes | Scraper written against verified markup |
| CarGurus | flagged | `local_capable`, scraper not yet written |
| cinch, Arnold Clark, Evans Halshaw, Big Motoring World, The Car People | flagged | `local_capable`, scrapers not yet written |
| AutoTrader | **no** | Use their saved-search email alert |
| eBay | n/a | Official API, works anywhere |

Sites flagged but without a scraper report
`local_mode on, but no scraper written for this site yet` and stay as deep
links. Adding one means writing a `fetch()` against that site's real markup —
see `MotorsSource` for the pattern and the verified-selector comment style.

## Bargain-hunting mode

As of July 2026 a 2021+ Polo Match 1.0 TSI 95PS with under 30k miles is roughly
a **£15,000–£16,500** car. Sampled listings: a 2021 Match 95PS DSG with 12,242
miles at £16,699; a 2021 Beats 95PS with 49,788 miles at £13,298.

At £14,000 with a 30k-mile cap you're at the lower edge of that range rather
than below it — a good-value car should now land in EXACT MATCH, and the
£16,000 stretch tier will show you what the market is genuinely asking so you
can judge whether something is a bargain.

To keep it from becoming inbox noise, `email.send_when_empty: false` means no
email is sent on a nothing-found day. You'll only hear from it when:

- something lands in EXACT MATCH or STRETCH BUDGET, or
- a car you've already seen **drops in price**, or
- a weekly heartbeat fires (`heartbeat_days: 7`) so you know it's alive

Reports are still written to `reports/` and committed every day either way, so
you can check it ran and build a price history.

If you'd rather widen the net, the levers in `config.yaml` are `budget.max_price`,
`budget.max_mileage` and `target.min_year`.

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
