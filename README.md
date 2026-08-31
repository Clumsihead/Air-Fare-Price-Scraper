# SIH Airfare Feasibility Scraper — IndiGo (first test source)

Technical-feasibility test for the SIH Indian Domestic Airfare Price Index
project, implementing the **Standard Technical Validation Protocol**
(Section 6) and **Validation Matrix** (Section 7) from
`Indian_Airfare_Source_Validation_Register.docx`, for the first source in
the register's priority list: **IndiGo**.

## Headline finding (checked before writing any adapter code)

`https://www.goindigo.in/robots.txt` explicitly disallows the entire
booking/search flow:

```
Disallow: /search.html
Disallow: /book.html
Disallow: /book/*
Disallow: /booking/*
Disallow: /bookings/*
Disallow: /booking-v1.html
Disallow: /book-flight.html
```

IndiGo's fare-search results are served from that flow. **This means
automated collection of IndiGo fares via their consumer site is not
permitted under their robots.txt**, and this tool is built to detect and
document that automatically rather than to work around it — per the
project's stated rule: *"Do not bypass CAPTCHAs, authentication, anti-bot
controls, paywalls or other access restrictions."*

Practically, that means:
- Running `run_feasibility_test.py --source indigo` should reach the
  homepage fine, but will halt with `suitability = NOT SUITABLE` and a
  documented `robots_txt_disallowed_paths` entry as soon as the search
  form submits into a `/book/...`-style results URL.
- The correct next step per the register's own "Immediate Next Step"
  (Section 9) is **not** to force IndiGo, but to request written
  permission from IndiGo, or move to the next Tier-A source in the list
  (Air India, Air India Express, Akasa Air, SpiceJet, MakeMyTrip,
  Goibibo, Yatra, EaseMyTrip, Cleartrip) and run the same tool against
  each with a new adapter.

One important implementation detail worth flagging: **Python's stdlib
`urllib.robotparser` does NOT correctly evaluate `Disallow: /book/*`
wildcard rules** (it only does literal prefix matching and would have
incorrectly reported IndiGo's booking pages as *allowed*). This project
uses [`protego`](https://github.com/scrapy/protego) — the parser Scrapy
uses — instead. This was verified directly against IndiGo's real,
currently-published robots.txt (see `tests/test_robots_gate.py`).

## Project layout

```
airfare_scraper/
  config.py              # SearchConfig (route/date/pax) + RunConfig (ops/ethics settings)
  robots_checker.py       # protego-based robots.txt gate, fails closed on fetch errors
  models.py                # FareObservation + FeasibilityReport (Section 7 matrix) data models
  adapters/
    base.py                 # BaseAirfareAdapter — shared orchestration (robots gate,
                             # screenshotting, raw HTML capture, repeat-query stability
                             # testing, feasibility-report assembly). New sources only
                             # need to subclass this.
    indigo.py                # IndiGo-specific selectors / extraction logic
  utils/
    logger.py, storage.py
  tests/
    test_robots_gate.py       # offline test proving the robots gate blocks IndiGo's
                                # booking flow, using a real captured robots.txt snapshot
  run_feasibility_test.py       # CLI entrypoint
  requirements.txt
  output/                        # created at runtime
    raw_html/     screenshots/     json/     reports/
```

### Adding the next source (e.g. Air India, MakeMyTrip)

1. Create `adapters/airindia.py` subclassing `BaseAirfareAdapter`.
2. Implement `home_url`, `fill_search_form()`, `wait_for_results()`,
   `extract_fares()`.
3. Register it in `ADAPTERS` in `run_feasibility_test.py`.

You get robots.txt gating, screenshots, raw HTML capture, repeat-query
stability testing, and the Section-7 feasibility report for free.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m playwright install chromium   # downloads the browser binary Playwright drives
```

## First run

Run **headed** the first time so you can watch what the search widget
actually does — the selectors in `adapters/indigo.py` are best-effort
(written from the public page structure, not verified against a live
render in the development sandbox used to build this) and will likely
need small adjustments (open devtools, confirm the real
`data-testid`/class names, update the selector lists in `indigo.py`):

```bash
python run_feasibility_test.py --source indigo --headed --repeat 1 \
  --contact-email you@yourorg.example
```

Then run the real test matched to the register's protocol (T+7 advance
purchase, repeat for stability):

```bash
python run_feasibility_test.py --source indigo \
  --origin DEL --destination BOM --days-ahead 7 --repeat 3 \
  --contact-email you@yourorg.example
```

### What gets written

- `output/reports/IndiGo_feasibility_report.json` — the full Section-7
  validation matrix result: robots.txt status, suitability verdict,
  step-by-step audit log, which fields were actually captured.
- `output/reports/IndiGo_robots_snapshot.txt` — the exact robots.txt text
  evaluated for this run (for reproducibility/audit).
- `output/raw_html/*.html` — full page HTML at the point of extraction
  (only saved for URLs robots.txt actually permits reaching).
- `output/screenshots/*.png` — full-page screenshots at each key step,
  including of any block encountered (for debugging, never for evidence
  of a bypass).
- `output/json/*.json` — structured fare observations per attempt.

### Offline test (no network / no browser needed)

```bash
python tests/test_robots_gate.py
```

Proves the robots gate correctly flags IndiGo's `/book/*`, `/booking/*`,
`/bookings/*` and `/search.html` paths as disallowed, and the homepage as
allowed, using a real captured snapshot of their robots.txt.

## Ethical/operational guardrails built into the code (not just documentation)

- `RunConfig` has hard `attempt_captcha_bypass=False` /
  `attempt_auth_bypass=False` / `attempt_antibot_bypass=False` flags —
  there is no code path that reads these to do the opposite; they exist
  so any future contributor sees the policy in the config itself.
- `RobotsGate` **fails closed**: if robots.txt can't be fetched or
  parsed, the URL is treated as disallowed, not allowed.
- Every run checks robots.txt **twice**: once for the entry URL before
  the browser even opens, and again for the *actual* URL reached after
  the search form submits (SPA search flows often land on a more
  restricted path than the homepage — exactly what happens with IndiGo).
- `detect_access_block()` scans for CAPTCHA/anti-bot/login-wall textual
  signals and raises `BlockedByAccessControl` — which **stops the run and
  documents it**, it is never caught-and-retried-around.
- A configurable `request_delay_seconds` (default 3s) is applied between
  repeat queries so the tool never hammers a site even where access is
  permitted.
- Raw HTML/screenshots are only ever saved for pages the robots.txt gate
  already cleared — the tool doesn't capture evidence from a page it
  wasn't permitted to load.

## Known limitations of this deliverable

- `adapters/indigo.py`'s CSS selectors are best-effort and were **not**
  verified against a live browser render while building this (the
  development sandbox's network egress allow-list does not include
  `goindigo.in`; only `robots.txt` could be fetched, via `web_fetch`, and
  Playwright itself was smoke-tested against an allowed domain to confirm
  the browser automation plumbing works). Expect to adjust selectors
  after the first `--headed` run.
- Given the robots.txt finding above, IndiGo is expected to report
  `NOT SUITABLE` for direct-site automation regardless of selector
  accuracy, once the search form submits into `/book/...`. The adapter
  code is still complete and correct so it (a) produces real, defensible
  evidence of *why*, and (b) is ready to point at a source whose
  robots.txt permits the equivalent flow.
