"""Small JSON-file state store so the watcher doesn't re-email every 5 minutes."""

from __future__ import annotations

import json
import logging
import os

from blue_lagoon_watcher import config

log = logging.getLogger(__name__)


def load() -> dict:
    if not os.path.exists(config.STATE_PATH):
        return {}
    try:
        with open(config.STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("Could not read state file, starting fresh", exc_info=True)
        return {}


def save(state: dict) -> None:
    with open(config.STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def should_notify(state: dict, hotel_slug: str, currently_available: bool) -> bool:
    """
    Rising-edge notification with periodic reminders:
    - First time a hotel becomes available -> notify.
    - Stays available -> notify again every REMINDER_EVERY_N_RUNS checks.
    - Becomes unavailable -> reset, so the next time it opens up we notify again.
    """
    entry = state.setdefault(hotel_slug, {"available": False, "streak": 0})

    if not currently_available:
        entry["available"] = False
        entry["streak"] = 0
        return False

    was_available = entry.get("available", False)
    entry["available"] = True
    entry["streak"] = entry.get("streak", 0) + 1

    if not was_available:
        return True
    return entry["streak"] % config.REMINDER_EVERY_N_RUNS == 0
