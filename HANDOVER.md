# PoloFinder — where you left off

**Last session: Sat 18 July 2026.** Everything below is on disk at
`D:\Claude\Projects\polofinder`. Most of it is **uncommitted** — see step 0.

---

## 0. First thing tomorrow

```bash
cd /d/claude/projects/polofinder
rm -f .git/index.lock          # stale lock keeps reappearing; harmless
git add -A
git commit -m "Self-hosted runner support, Motors scraper, EVO fix, mileage fix"
git push
```

If `git add` fails with "index.lock exists", delete
`D:\Claude\Projects\polofinder\.git\index.lock` in Explorer (enable Hidden items).

Sanity check before anything else — should print **78 passed**:

```bash
python -m pytest tests/ -q
```

---

## 1. Two real cars found — act on these before more automation

Both are **1.0 TSI Match, 2021, post-facelift** — genuinely your spec.
Neither advert mentions a **rear camera**; worth asking both directly.

### Gloucester — 9 miles away
**https://www.motors.co.uk/car-79060436/**
£13,900 · 22,235 miles · 2021 (21) · Mon Motors Volkswagen Gloucester ·
**01452 227271** · history check all passed · 16" alloys, sensors, cruise ·
insurance group 8 · 61 MPG

### Bristol — 36 miles away
**https://www.autotrader.co.uk/car-details/202606123226668**
£13,199 · 23,682 miles · 2021 (21) · Carbase Bristol · **01934 611038** ·
1 owner from new · 4 service stamps (last at 23k) · RAC multi-point inspection ·
front+rear parking sensors, Apple CarPlay/Android Auto, 8" screen, DAB,
Front Assist · 15" alloys · "Great price" · no-haggle pricing

**Ask both:** owner count, full service history, rear camera fitted?,
Climatronic or basic air con, and whether it's the 95PS (not 110PS).

### The EVO trap — important
AutoTrader and Motors both list **"1.0 EVO Match"** alongside "1.0 TSI Match",
a few hundred pounds cheaper. **EVO is the 80PS naturally-aspirated engine**,
not the 95PS turbo. At least five of the cheapest "Match" listings were EVOs.
The matcher now rejects them, but watch for it when browsing manually.

---

## 2. Runner setup — NOT DONE, needs you

The workflow file exists (`.github/workflows/self-hosted.yml`) but no runner is
registered, so nothing runs on a schedule yet.

You already have an `actions-runner` directory for another repo. You **cannot**
reuse it — one registration per directory, and sharing runners across repos is
an org-only feature (psykalist is a personal account). Copy it:

```powershell
Copy-Item -Recurse C:\actions-runner C:\actions-runner-polofinder
cd C:\actions-runner-polofinder
Remove-Item .runner, .credentials, .credentials_rsaparams, _diag -Force -Recurse -ErrorAction SilentlyContinue
./config.cmd --url https://github.com/psykalist/Polofinder --token YOUR_TOKEN --name polofinder --runasservice
```

Token (short-lived, grab it just before running):
https://github.com/psykalist/Polofinder/settings/actions/runners/new

Test the local scrape first — no point registering a runner if this returns nothing:

```bash
POLOFINDER_LOCAL_MODE=1 python -m polofinder.run --no-email --only motors --debug
```

---

## 3. Still outstanding

### Blocking — nothing emails until these are set
- [ ] **SMTP secrets** — `SMTP_USER`, `SMTP_PASS` (Gmail **App Password**, not
      your login password) at Settings → Secrets and variables → Actions
- [ ] **Machine must be awake at 08:00** — Settings → System → Power → Sleep

### High value
- [ ] **eBay API keys** — free at https://developer.ebay.com → `EBAY_APP_ID`,
      `EBAY_CERT_ID`. This is the single biggest improvement available. Only
      source with real server-side filtering. Currently errors out.
- [ ] **AutoTrader saved search** — deliberately NOT scraped (their ToS
      prohibits it). Set up their native email alert on this URL instead:
      https://www.autotrader.co.uk/car-search?postcode=GL530ES&radius=200&make=VOLKSWAGEN&model=POLO&price-to=16000&maximum-mileage=30000&year-from=2021&fuel-type=Petrol&exclude-writeoff-categories=on&sort=price-asc
      570 results, best inventory of any site. Free, instant, no maintenance.

### Known problems
- [ ] **Gumtree returns junk.** 31 results, mostly 2007–2017 cars. robots.txt
      allows only ONE query param and blocks pagination, and the
      `vehicle_mileage=up_to_30000` filter isn't being applied — value format
      is wrong and unverified. Structurally a weak source.
- [ ] **Motors drops URL filters.** Redirects to bare `/search/car/` with 3,908
      unfiltered results. Sorted by distance though, so nearest-first is
      usable. Everything filtered client-side.
- [ ] **carwow deep link was dead** (`/used-cars/volkswagen/polo` 404s). Now
      points at the landing page.
- [ ] **8 deep links never verified.** Only AutoTrader, Motors and carwow have
      been opened. CarGurus, heycar, cinch, Arnold Clark, Evans Halshaw,
      Big Motoring World, The Car People — click them and check.
- [ ] **No scrapers for CarGurus / dealer groups.** Flagged `local_capable` but
      report "no scraper written yet". Pattern to follow: `MotorsSource` in
      `polofinder/sources/sites.py`, with verified selectors in the docstring.
- [ ] **Two workflows will double-email.** `daily.yml` (cloud) and
      `self-hosted.yml` both run at 08:00. Disable one.

---

## 4. Config decisions made

| Setting | Value | Why |
|---|---|---|
| `max_price` | £14,000 | Raised from £12,500 |
| `stretch_price` | £16,000 | Shows what the market actually asks |
| `max_mileage` | 30,000 | **Now the binding constraint, not price** |
| `min_year` | 2021 | Facelift only; Life sits below Match |
| `postcode` | GL53 0ES | Distance shown per car |
| `send_when_empty` | false | No email on nothing-found days |
| `heartbeat_days` | 7 | Weekly keep-alive so you know it's running |
| `local_mode` | false | Flipped to true by the self-hosted workflow |

**Correction from last session:** I told you £12,500 was below market. That was
wrong — based on two search results, not real inventory. AutoTrader has Match
cars from £11,995. Your original budget was fine; £14k just widens the field.

If EXACT MATCH stays empty for weeks, loosen **mileage** before price.

---

## 5. Useful commands

```bash
python -m polofinder.run --no-email --debug        # full run, no email
python -m polofinder.run --only motors --debug     # one source
POLOFINDER_LOCAL_MODE=1 python -m polofinder.run --no-email   # local scraping
python diagnose_gumtree.py --show                  # visible browser, saves HTML
python -m pytest tests/ -q                         # 78 tests
```

Reports land in `reports/` — `latest.html` opens in a browser.
