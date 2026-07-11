# Blue Lagoon Availability Watcher

Checks bluelagoon.com every 5 minutes for a suite (>= 500 sq ft) for the
stay **2026-07-20 → 2026-07-22 (2 adults)**, at **The Retreat Hotel**
(preferred) and **Silica Hotel** (fallback). Emails asnarun75@gmail.com
the moment one shows up, with a link back to the booking search.

## How it runs

`.github/workflows/blue_lagoon_watch.yml` runs on a `*/5 * * * *` cron plus
a manual `workflow_dispatch` trigger.

**GitHub only fires scheduled workflows from the repository's default
branch (`main`).** Nothing runs on a schedule until this is pushed there —
which it is by default in this repo. You can also trigger it manually from
the Actions tab ("Run workflow") to test it.

GitHub Actions also silently disables scheduled workflows after 60 days
with no repository activity — a commit (even unrelated) resets that clock.

## One-time setup: email secrets

The workflow sends email via Gmail SMTP, which needs an **App Password**
(not your normal Gmail password — Google blocks plain-password SMTP login).

1. Turn on 2-Step Verification on the sending Gmail account, if not already on:
   https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
   (choose "Mail" / "Other", copy the 16-character password)
3. In this repo: **Settings → Secrets and variables → Actions → New repository secret**,
   add:
   - `GMAIL_USER` — the Gmail address you generated the app password for
     (can be asnarun75@gmail.com itself, or a separate account used just for sending)
   - `GMAIL_APP_PASSWORD` — the 16-character app password
   - `NOTIFY_EMAIL` — optional, defaults to `asnarun75@gmail.com` if unset

Without these secrets the checker still runs and logs what it finds, it just
can't email you.

## Known limitations (read before relying on this)

- **Selectors are best-effort, not verified against the live site.** The
  scraper (`blue_lagoon_watcher/scraper.py`) uses two fallback strategies —
  parsing embedded page JSON, then a text/keyword heuristic — instead of
  hand-picked CSS selectors, because the environment this was built in has
  no network access to bluelagoon.com. **Run it once manually (Actions tab
  → "Run workflow") and check the `blue-lagoon-debug` artifact** (screenshot
  + saved HTML per hotel) to confirm it's actually finding room cards. If a
  run reports zero matches but rooms are visibly available on the site,
  share the debug HTML so the parsing logic can be tuned to the real markup.
- **"The Retreat" hotel slug is a guess** (`retreat`, following the same
  `/book/hotel/{slug}` pattern as the Silica link this was built from). If
  that 404s or redirects, update `HOTELS` in `blue_lagoon_watcher/config.py`
  with the correct slug.
- **No auto-booking or payment.** This does not fill in guest details or
  reach a credit-card page — doing that reliably without a verified DOM
  would risk creating spurious reservation holds. The email includes a
  direct link back to the search/results page so you can complete booking
  by hand within seconds of the alert.
- Automated polling of a commercial booking site may be against its Terms
  of Service — this is intended for personal, low-frequency use (5-minute
  interval, single search), not scraping at scale.

## Local dry run

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=xxxx python -m blue_lagoon_watcher.agent
```

## Files

- `blue_lagoon_watcher/config.py` — dates, guests, hotels, size threshold, reminder cadence
- `blue_lagoon_watcher/scraper.py` — Playwright-driven fetch + parse per hotel
- `blue_lagoon_watcher/notifier.py` — Gmail SMTP email sender
- `blue_lagoon_watcher/state.py` — `state.json` persistence so you get one alert on new
  availability plus a reminder every ~hour it stays open, not one email
  every 5 minutes
- `blue_lagoon_watcher/agent.py` — entrypoint (`python -m blue_lagoon_watcher.agent`)
