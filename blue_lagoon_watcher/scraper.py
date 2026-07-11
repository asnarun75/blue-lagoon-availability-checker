"""
Blue Lagoon hotel availability scraper.

bluelagoon.com/book is a JS-rendered booking widget, so we drive it with a
headless browser (Playwright) rather than plain requests. Because room-card
markup can't be inspected from this sandbox (network policy blocks
bluelagoon.com here), extraction uses two layers, from most to least precise:

1. Structured data: many booking widgets embed the room/rate list as JSON in
   a script tag (Next.js __NEXT_DATA__, __NUXT__, or a window.__INITIAL_STATE__
   -style blob). We scan every <script> tag for JSON and walk it looking for
   objects that look like room entries (a name plus a size-like field).
2. Text heuristic fallback: scan the rendered page's visible text for blocks
   that mention a room keyword (e.g. "suite") near a size figure
   (e.g. "550 sq ft" / "51 m²") and near an availability/booking control.

If neither layer finds anything, the run is treated as "no match" rather than
an error, and a screenshot + HTML snapshot are saved to DEBUG_DIR so the
selectors/heuristics can be tuned from the GitHub Actions debug artifact.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass, field

from blue_lagoon_watcher import config

log = logging.getLogger(__name__)

_SQFT_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|square\s+feet|sqft)", re.I)
_SQM_RE  = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:m²|m2|sq\.?\s*m|square\s+met(?:er|re)s?)", re.I)
_SOLD_OUT_WORDS = ("sold out", "no availability", "unavailable", "not available", "waitlist")
_BOOKABLE_WORDS = ("select room", "select", "book now", "choose room", "add to cart", "reserve", "continue")


@dataclass
class RoomMatch:
    hotel_slug: str
    hotel_name: str
    room_name: str
    sqft: float | None
    price: str | None
    available: bool
    source_url: str
    booking_url: str | None = None


@dataclass
class HotelCheckResult:
    hotel_slug: str
    hotel_name: str
    url: str
    matches: list[RoomMatch] = field(default_factory=list)
    error: str | None = None


def build_url(slug: str) -> str:
    rooms = json.dumps(
        [{"adults": config.ADULTS, "children": config.CHILDREN, "infants": config.INFANTS}],
        separators=(",", ":"),
    )
    params = {
        "from": f"{config.CHECK_IN}T00:00:00.000Z",
        "to":   f"{config.CHECK_OUT}T00:00:00.000Z",
        "rooms": rooms,
    }
    base = config.BASE_URL.format(slug=slug)
    return f"{base}?{urllib.parse.urlencode(params)}"


def _sqft_from_text(text: str) -> float | None:
    m = _SQFT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    m = _SQM_RE.search(text)
    if m:
        return float(m.group(1).replace(",", "")) * 10.7639  # m² -> sq ft
    return None


def _matches_room_keyword(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in config.ROOM_KEYWORDS)


def _looks_available(text: str) -> bool | None:
    t = text.lower()
    if any(w in t for w in _SOLD_OUT_WORDS):
        return False
    if any(w in t for w in _BOOKABLE_WORDS):
        return True
    return None  # unknown — caller decides how to treat this


def _walk_json_for_rooms(obj, hotel_slug: str, hotel_name: str, url: str, out: list[RoomMatch]) -> None:
    """Best-effort walk of an arbitrary JSON blob looking for room-like dicts."""
    if isinstance(obj, dict):
        name = None
        for key in ("name", "title", "roomName", "label"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                name = v.strip()
                break
        size = None
        for key in ("sizeSqft", "squareFeet", "sqft", "size", "areaSqft", "sizeInSqFt"):
            v = obj.get(key)
            if isinstance(v, (int, float)):
                size = float(v)
                break
            if isinstance(v, str):
                size = _sqft_from_text(v)
                if size:
                    break
        if size is None:
            for key in ("sizeSqm", "squareMeters", "areaSqm", "sizeInSqM"):
                v = obj.get(key)
                if isinstance(v, (int, float)):
                    size = float(v) * 10.7639
                    break

        if name and _matches_room_keyword(name):
            avail = None
            for key in ("available", "isAvailable", "inStock", "soldOut", "isSoldOut"):
                v = obj.get(key)
                if isinstance(v, bool):
                    avail = (not v) if key.lower().startswith(("soldout", "issoldout")) else v
                    break
            price = None
            for key in ("price", "totalPrice", "priceFormatted", "amount"):
                v = obj.get(key)
                if v is not None:
                    price = str(v)
                    break
            if avail is None:
                avail = True  # present in a rooms/rates list generally implies bookable
            out.append(RoomMatch(
                hotel_slug=hotel_slug, hotel_name=hotel_name, room_name=name,
                sqft=size, price=price, available=bool(avail), source_url=url,
            ))

        for v in obj.values():
            _walk_json_for_rooms(v, hotel_slug, hotel_name, url, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json_for_rooms(item, hotel_slug, hotel_name, url, out)


def _extract_from_scripts(page, hotel_slug: str, hotel_name: str, url: str) -> list[RoomMatch]:
    found: list[RoomMatch] = []
    scripts = page.eval_on_selector_all("script", "els => els.map(e => e.textContent || '')")
    for raw in scripts:
        raw = raw.strip()
        if not raw or len(raw) < 20:
            continue
        candidate = raw
        # Next.js: window.__NEXT_DATA__ = {...}
        m = re.search(r"__NEXT_DATA__\s*=\s*(\{.*\})\s*;?\s*$", raw, re.S)
        if m:
            candidate = m.group(1)
        elif not (candidate.startswith("{") or candidate.startswith("[")):
            continue
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        _walk_json_for_rooms(data, hotel_slug, hotel_name, url, found)
    return found


def _extract_from_text(page, hotel_slug: str, hotel_name: str, url: str) -> list[RoomMatch]:
    found: list[RoomMatch] = []
    try:
        candidates = page.eval_on_selector_all(
            "[class*='room'], [class*='rate'], [class*='plan'], [data-testid*='room']",
            "els => els.map(e => e.innerText || '')",
        )
    except Exception:
        candidates = []
    if not candidates:
        body_text = page.inner_text("body")
        candidates = [body_text]

    for text in candidates:
        if not text or not _matches_room_keyword(text):
            continue
        sqft = _sqft_from_text(text)
        avail = _looks_available(text)
        if sqft is None and avail is None:
            continue  # too little signal to trust this block
        first_line = next((l.strip() for l in text.splitlines() if l.strip()), text[:80])
        found.append(RoomMatch(
            hotel_slug=hotel_slug, hotel_name=hotel_name, room_name=first_line,
            sqft=sqft, price=None, available=bool(avail) if avail is not None else True,
            source_url=url,
        ))
    return found


def check_hotel(hotel_slug: str, hotel_name: str, headless: bool = True) -> HotelCheckResult:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

    url = build_url(hotel_slug)
    result = HotelCheckResult(hotel_slug=hotel_slug, hotel_name=hotel_name, url=url)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ))
            try:
                page.goto(url, wait_until="networkidle", timeout=45_000)
            except PWTimeoutError:
                page.wait_for_timeout(3_000)  # site may never go fully idle; proceed anyway

            matches = _extract_from_scripts(page, hotel_slug, hotel_name, url)
            if not matches:
                matches = _extract_from_text(page, hotel_slug, hotel_name, url)

            _save_debug(page, hotel_slug)
            browser.close()

        result.matches = [
            m for m in matches
            if m.sqft is None or m.sqft >= config.MIN_SQFT
        ]
    except Exception as exc:  # keep one hotel's failure from killing the whole run
        log.exception("Failed checking %s", hotel_name)
        result.error = str(exc)

    return result


def _save_debug(page, hotel_slug: str) -> None:
    try:
        os.makedirs(config.DEBUG_DIR, exist_ok=True)
        page.screenshot(path=os.path.join(config.DEBUG_DIR, f"{hotel_slug}.png"), full_page=True)
        with open(os.path.join(config.DEBUG_DIR, f"{hotel_slug}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        log.warning("Could not save debug artifacts for %s", hotel_slug, exc_info=True)
