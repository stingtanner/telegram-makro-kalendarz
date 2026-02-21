"""
Telegram public channel macro calendar (HIGH) - free sources, best-effort.

Key design:
- Runs daily (GitHub Actions) and posts events for: today->end of week; on Saturday posts next week.
- Only "high impact" by curated keyword rules (because free official sources rarely provide impact ratings).
- Uses best-effort HTTP fetching with browser-like headers.
- IMPORTANT: any blocked source (403/timeout/etc.) is skipped, never crashes the run.
"""

from __future__ import annotations

import os
import sys
import time
import json
import textwrap
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Iterable, List, Dict, Tuple

import requests
from bs4 import BeautifulSoup
from dateutil import tz
from dateutil import parser as dateparser

# -------------------- Config --------------------

WARSAW_TZ = tz.gettz("Europe/Warsaw")

MAJOR_CCY = {"USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD"}

# We'll tag the channel with these extra instruments (user request)
EXTRA_TAGS = ["#XAU", "#XAG", "#NAS100"]

# "High impact" keyword rules (English)
HIGH_KEYWORDS = [
    "CPI", "Consumer Price", "Inflation",
    "GDP", "Gross Domestic Product",
    "Nonfarm", "Employment", "Unemployment", "Payroll",
    "Retail Sales",
    "Interest Rate", "Rate Decision", "Monetary Policy",
    "FOMC", "ECB", "BoE", "BoJ", "SNB", "BoC", "RBA", "RBNZ",
    "Press Conference", "Policy Statement", "Monetary Policy Statement",
]

# Source list (best-effort). Some may block GitHub runners — we will skip if blocked.
# We prefer official sources, but will not crash if they 403.
SOURCES = [
    # Central bank calendars / schedules (HTML)
    ("USD", "FOMC (Federal Reserve) calendar", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    ("EUR", "ECB press calendar (monetary policy)", "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"),
    ("GBP", "BoE MPC dates (Bank of England)", "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes"),
    ("JPY", "BoJ policy meeting schedule", "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"),
    ("CHF", "SNB event schedule", "https://www.snb.ch/en/services-events/digital-services/event-schedule"),
    ("CAD", "Bank of Canada key interest rate dates", "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/"),
    ("AUD", "RBA board meeting schedule", "https://www.rba.gov.au/schedules-events/board-meeting-schedules.html"),
    ("NZD", "RBNZ OCR decision dates", "https://www.rbnz.govt.nz/news-and-events/how-we-release-information/ocr-decision-dates-and-financial-stability-report-dates-to-feb-2028"),
    # US releases schedules (HTML) - may block; still try
    ("USD", "BLS releases (schedule)", "https://www.bls.gov/schedule/news_release/current_year.asp"),
    ("USD", "BEA schedule", "https://www.bea.gov/news/schedule"),
    ("USD", "Census economic indicators", "https://www.census.gov/economic-indicators/"),
]

# Telegram limits: 4096 chars for text messages
TG_LIMIT = 3900  # keep margin

# -------------------- Data model --------------------

@dataclass
class Event:
    dt: Optional[datetime]  # local Warsaw time if available
    ccy: str
    title: str
    source: str

# -------------------- Time window --------------------

def warsaw_now() -> datetime:
    return datetime.now(tz=WARSAW_TZ)

def week_window(today: date) -> Tuple[date, date]:
    # python weekday: Mon=0..Sun=6
    wd = today.weekday()
    if wd == 5:  # Saturday -> next week
        start = today + timedelta(days=2)
        end = start + timedelta(days=6)
    else:
        start = today
        end = today + timedelta(days=(6 - wd))
    return start, end

# -------------------- HTTP helpers --------------------

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    "Connection": "close",
}

def http_get(url: str, timeout: int = 30, max_tries: int = 3, backoff: float = 1.6) -> Optional[str]:
    last_err = None
    for i in range(max_tries):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            # If blocked, return None (do not crash)
            if r.status_code in (401,403,429):
                return None
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(backoff ** i)
    # final fail -> None
    return None

# -------------------- Parsing (best-effort) --------------------

def looks_high(title: str) -> bool:
    t = title.lower()
    for kw in HIGH_KEYWORDS:
        if kw.lower() in t:
            return True
    return False

def parse_dates_from_text(text: str) -> List[date]:
    """Try to extract a concrete calendar date from arbitrary text.

    We keep this intentionally conservative:
    - If we can't parse a date, return [] (caller will skip the item).
    - If we can parse, return [date].
    """
    try:
        # Use a stable default so parser doesn't "invent" today's date from partial strings
        default_dt = datetime(2000, 1, 1, 0, 0, tzinfo=WARSAW_TZ)
        dt = dateparser.parse(text, fuzzy=True, dayfirst=True, default=default_dt)
        if not dt:
            return []
        # If the parser returned the default date (meaning it likely failed), discard.
        if dt.year == 2000 and dt.month == 1 and dt.day == 1:
            return []
        return [dt.astimezone(WARSAW_TZ).date() if dt.tzinfo else dt.date()]
    except Exception:
        return []

def extract_events_generic(ccy: str, source_name: str, url: str, start: date, end: date) -> List[Event]:
    html = http_get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    # Collect candidate lines with dates
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    events: List[Event] = []

    # simple heuristic:
    # - keep only lines that look HIGH
    # - try to parse a *concrete* date from the line
    # - keep only events that fall within [start, end]
    month_names = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    seen: set[tuple[str, str]] = set()
    for ln in lines:
        low = ln.lower()
        if not looks_high(ln):
            continue
        if not (any(m in low for m in month_names) and any(ch.isdigit() for ch in low)):
            continue

        dates = parse_dates_from_text(ln)
        if not dates:
            continue

        for d in dates:
            if d < start or d > end:
                continue
            dt = datetime(d.year, d.month, d.day, 0, 0, tzinfo=WARSAW_TZ)
            key = (ccy, ln[:180])
            if key in seen:
                continue
            seen.add(key)
            events.append(Event(dt=dt, ccy=ccy, title=ln[:180], source=source_name))

    return events

def collect_events(start: date, end: date) -> List[Event]:
    out: List[Event] = []
    for ccy, name, url in SOURCES:
        # only major currencies
        if ccy not in MAJOR_CCY:
            continue
        try:
            out += extract_events_generic(ccy, name, url, start, end)
        except Exception:
            # Never crash on source parsing
            continue
    return out

# -------------------- Telegram posting --------------------

def tg_send(text: str) -> None:
    token = os.environ["TG_BOT_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()

def split_messages(text: str, limit: int = TG_LIMIT) -> List[str]:
    parts: List[str] = []
    cur = ""
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        candidate = (cur + ("\n\n" if cur else "") + block)
        if len(candidate) <= limit:
            cur = candidate
        else:
            if cur:
                parts.append(cur)
                cur = block
            else:
                # single block too large -> hard split
                for i in range(0, len(block), limit):
                    parts.append(block[i:i+limit])
                cur = ""
    if cur:
        parts.append(cur)
    return parts

def format_post(start: date, end: date, events: List[Event]) -> str:
    now = warsaw_now()
    header = f"📅 Kalendarz makro (HIGH) — {start.isoformat()} → {end.isoformat()} (Warszawa)\n"
    header += "Waluty: " + ", ".join(sorted(MAJOR_CCY)) + "\n"
    header += "Dodatkowo: " + " ".join(EXTRA_TAGS) + "\n"
    header += "Źródła: oficjalne strony instytucji (best‑effort; jeśli któraś blokuje automaty, jest pomijana)."

    # If no dated data, still publish undated highlights
    # Deduplicate titles
    seen = set()
    items = []
    for ev in events:
        key = (ev.ccy, ev.title)
        if key in seen:
            continue
        seen.add(key)
        flag = {
            "USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","JPY":"🇯🇵","CHF":"🇨🇭","CAD":"🇨🇦","AUD":"🇦🇺","NZD":"🇳🇿"
        }.get(ev.ccy, "🏳️")
        items.append(f"• {flag} {ev.ccy} — {ev.title}\n  ({ev.source})")

    if not items:
        body = "\n\nBrak danych HIGH do pokazania (albo część źródeł zablokowała pobieranie z GitHuba)."
    else:
        body = "\n\n" + "\n".join(items[:120])

    footer = "\n\n#forex #kalendarz #highimpact " + " ".join(EXTRA_TAGS)
    return header + body + footer

def main() -> int:
    today = warsaw_now().date()
    start, end = week_window(today)

    events = collect_events(start, end)
    post = format_post(start, end, events)

    parts = split_messages(post, TG_LIMIT)
    for idx, part in enumerate(parts, 1):
        if len(parts) > 1:
            part = f"(część {idx}/{len(parts)})\n\n" + part
        tg_send(part)
        time.sleep(1.0)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())