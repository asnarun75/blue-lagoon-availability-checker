"""
Email notifications via Gmail SMTP.

Requires GMAIL_USER (the sending account) and GMAIL_APP_PASSWORD (a 16-char
Google App Password, not the account's normal login password — see README.md
for setup) supplied as environment variables / GitHub Actions secrets.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from blue_lagoon_watcher import config
from blue_lagoon_watcher.scraper import HotelCheckResult

log = logging.getLogger(__name__)


def _format_body(results: list[HotelCheckResult]) -> str:
    lines = [
        f"Blue Lagoon availability check — stay {config.CHECK_IN} to {config.CHECK_OUT} "
        f"({config.ADULTS} adults), suites >= {config.MIN_SQFT} sq ft.",
        "",
    ]
    for r in results:
        if not r.matches:
            continue
        lines.append(f"== {r.hotel_name} ==")
        for m in r.matches:
            size = f"{m.sqft:.0f} sq ft" if m.sqft else "size unknown"
            price = f" — {m.price}" if m.price else ""
            lines.append(f"  * {m.room_name} ({size}){price}")
            if m.booking_url:
                lines.append(f"    Booking link: {m.booking_url}")
        lines.append(f"  Search page: {r.url}")
        lines.append("")
    lines.append("This is an automated check running every 5 minutes. Book quickly — suite availability can disappear fast.")
    return "\n".join(lines)


def send_availability_email(results: list[HotelCheckResult]) -> None:
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        log.error(
            "GMAIL_USER / GMAIL_APP_PASSWORD not configured — cannot send email. "
            "Availability was found but no notification was sent. See README.md."
        )
        return

    hotel_names = ", ".join(r.hotel_name for r in results if r.matches)
    subject = f"Blue Lagoon: suite available at {hotel_names}"
    body = _format_body(results)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.NOTIFY_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
            smtp.sendmail(config.GMAIL_USER, [config.NOTIFY_EMAIL], msg.as_string())
        log.info("Notification email sent to %s", config.NOTIFY_EMAIL)
    except smtplib.SMTPException:
        log.exception("Failed to send notification email")
