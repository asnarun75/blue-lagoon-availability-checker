"""
User preferences — edit these before running.
"""

import os

# ── Stay dates ──────────────────────────────────────────────────────────────
CHECK_IN  = "2026-07-20"
CHECK_OUT = "2026-07-22"

# ── Guests (matches the search you gave us) ──────────────────────────────────
ADULTS   = 2
CHILDREN = 0
INFANTS  = 0

# ── Room filter ───────────────────────────────────────────────────────────────
MIN_SQFT      = 500
ROOM_KEYWORDS = ["suite"]   # room name must contain one of these (case-insensitive)

# ── Hotels to check, in priority order ────────────────────────────────────────
# "retreat" is checked first because it's the preferred property; "silica" is
# the fallback. If bluelagoon.com uses a different slug for The Retreat, update
# it here after the first dry run (see debug artifact in the GitHub Action).
HOTELS = [
    {"slug": "retreat", "name": "The Retreat Hotel"},
    {"slug": "silica",  "name": "Silica Hotel"},
]

BASE_URL = "https://www.bluelagoon.com/book/hotel/{slug}"

# ── Notification ──────────────────────────────────────────────────────────────
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "asnarun75@gmail.com")
GMAIL_USER          = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")

# Once availability is found, keep sending a reminder every N runs (so a
# 5-minute cron sends a reminder roughly once an hour) instead of emailing
# every single run while the room stays open.
REMINDER_EVERY_N_RUNS = 12

STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")
DEBUG_DIR  = os.path.join(os.path.dirname(__file__), "debug")
