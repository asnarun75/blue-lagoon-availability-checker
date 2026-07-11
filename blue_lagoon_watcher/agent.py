"""
Entry point: `python -m blue_lagoon_watcher.agent`

Checks each configured hotel for a suite >= MIN_SQFT for the configured
dates, emails NOTIFY_EMAIL on new availability, and persists state.json so
repeated runs don't spam the inbox.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys

from blue_lagoon_watcher import config, notifier, scraper, state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _stay_window_passed() -> bool:
    today = dt.datetime.now(dt.timezone.utc).date()
    checkout = dt.date.fromisoformat(config.CHECK_OUT)
    return today > checkout


def main() -> int:
    if _stay_window_passed():
        log.info("Check-out date %s has passed — nothing to watch, exiting.", config.CHECK_OUT)
        return 0

    st = state.load()
    results: list[scraper.HotelCheckResult] = []
    failures = 0

    for hotel in config.HOTELS:
        log.info("Checking %s ...", hotel["name"])
        result = scraper.check_hotel(hotel["slug"], hotel["name"])
        results.append(result)
        if result.error:
            failures += 1
            log.warning("%s: %s", hotel["name"], result.error)
        else:
            log.info("%s: %d matching room(s)", hotel["name"], len(result.matches))

    if failures == len(config.HOTELS):
        log.error("All hotel checks failed — likely a site/network issue, not 'no availability'.")
        return 1

    to_notify = [
        r for r in results
        if r.matches and state.should_notify(st, r.hotel_slug, currently_available=True)
    ]
    for r in results:
        if not r.matches:
            state.should_notify(st, r.hotel_slug, currently_available=False)

    if to_notify:
        notifier.send_availability_email(to_notify)
    else:
        log.info("No new availability to report this run.")

    state.save(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
