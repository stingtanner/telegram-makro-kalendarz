
from __future__ import annotations

import os
import re
import sys
import json
import math
import textwrap
from dataclasses import dataclass
from datetime import datetime, date, timedelta, time
from typing import Iterable, List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dateutil import tz
from dateutil.parser import parse as dtparse

# ----------------------------
# Models
# ----------------------------

@dataclass(frozen=True)
class Event:
    dt_local: datetime          # localized to config timezone
    currency: str               # USD/EUR/...
    title: str
    source: str                 # short label
    url: str

# ----------------------------
# Config
# ----------------------------

def load_config() -> dict:
    import yaml  # type: ignore
    here = os.path.dirname(__file__)
    cfg_path = os.path.join(os.path.dirname(here), "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_tz(tzname: str):
    z = tz.gettz(tzname)
    if z is None:
        raise RuntimeError(f"Nie znam strefy czasowej: {tzname}")
    return z

# ----------------------------
# Time window logic
# ----------------------------

def week_window(now_local: datetime, saturday_next_week: bool) -> Tuple[datetime, datetime]:
    """
    Returns [start, end] inclusive bounds for events: today -> end of week (Sunday 23:59:59).
    If saturday_next_week and today is Saturday: show next week Monday->Sunday.
    """
    today = now_local.date()
    weekday = now_local.weekday()  # Mon=0..Sun=6

    if saturday_next_week and weekday == 5:  # Saturday
        # Next Monday
        start_date = today + timedelta(days=2)
        end_date = start_date + timedelta(days=6)
    else:
        start_date = today
        end_date = today + timedelta(days=(6 - weekday))

    start_dt = datetime.combine(start_date, time(0, 0, 0), tzinfo=now_local.tzinfo)
    end_dt = datetime.combine(end_date, time(23, 59, 59), tzinfo=now_local.tzinfo)
    return start_dt, end_dt

# ----------------------------
# Helpers
# ----------------------------


def parse_ics_events(ics_text: str) -> List[dict]:
    """Very small ICS (iCalendar) parser for VEVENT DTSTART + SUMMARY + DESCRIPTION.
    Returns a list of dicts with keys: dtstart_raw, tzid, summary, description.
    """
    # Unfold lines (RFC5545): lines that start with space/tab continue previous line
    lines = ics_text.splitlines()
    unfolded: List[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    events: List[dict] = []
    cur: dict | None = None
    for line in unfolded:
        if line == "BEGIN:VEVENT":
            cur = {"summary": "", "description": "", "dtstart_raw": "", "tzid": None}
        elif line == "END:VEVENT":
            if cur and cur.get("dtstart_raw") and cur.get("summary"):
                events.append(cur)
            cur = None
        elif cur is not None:
            if line.startswith("DTSTART"):
                # Examples:
                # DTSTART:20260206T133000Z
                # DTSTART;TZID=America/New_York:20260206T083000
                left, _, value = line.partition(":")
                cur["dtstart_raw"] = value.strip()
                m = re.search(r"TZID=([^;:]+)", left)
                if m:
                    cur["tzid"] = m.group(1)
            elif line.startswith("SUMMARY:"):
                cur["summary"] = line[len("SUMMARY:"):].strip()
            elif line.startswith("DESCRIPTION:"):
                cur["description"] = line[len("DESCRIPTION:"):].strip()
    return events

def ics_dt_to_local(dt_raw: str, tzid: str | None, tz_local) -> Optional[datetime]:
    """Parse an ICS DTSTART value into tz_local datetime."""
    if not dt_raw:
        return None
    try:
        # Date only
        if len(dt_raw) == 8 and dt_raw.isdigit():
            dt = datetime.strptime(dt_raw, "%Y%m%d")
            dt = dt.replace(tzinfo=tz_local)
            return dt

        # Datetime with Z
        if dt_raw.endswith("Z"):
            dt = datetime.strptime(dt_raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
            return dt.astimezone(tz_local)

        # Datetime without Z
        dt = datetime.strptime(dt_raw, "%Y%m%dT%H%M%S" if len(dt_raw) >= 15 else "%Y%m%dT%H%M")
        if tzid:
            try:
                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(tzid))
            except Exception:
                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
        else:
            dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
        return dt.astimezone(tz_local)
    except Exception:
        return None


def http_get(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TelegramCalendarBot/1.0; +https://github.com/)"
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def match_high(title: str, currency: str, high_keywords: Dict[str, List[str]]) -> bool:
    kws = high_keywords.get(currency, [])
    t = title.lower()
    return any(k.lower() in t for k in kws)

def split_telegram(text: str, max_len: int) -> List[str]:
    """
    Splits message into chunks <= max_len, trying to split on double newlines or newlines.
    """
    if len(text) <= max_len:
        return [text]
    parts = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts

# ----------------------------
# Sources (official / public)
# ----------------------------


def fetch_bls_selected_releases(tz_local, start: datetime, end: datetime) -> List[Event]:
    """
    BLS provides an official iCalendar (.ics) feed for its release calendar.
    We use the ICS feed instead of scraping HTML (HTML may return 403 in CI environments).
    """
    url = "https://www.bls.gov/schedule/news_release/bls.ics"
    ics_text = http_get(url)
    vevents = parse_ics_events(ics_text)

    events: List[Event] = []
    for ve in vevents:
        dt_local = ics_dt_to_local(ve.get("dtstart_raw", ""), ve.get("tzid"), tz_local)
        if not dt_local:
            continue
        if dt_local < start or dt_local > end:
            continue

        title = ve.get("summary", "").strip()
        if not title:
            continue

        # Most BLS releases are USD-relevant.
        events.append(Event(
            source="BLS",
            title=title,
            currency="USD",
            country="US",
            impact="HIGH",  # we only pick 'high' later via keyword filters; keep as HIGH marker
            dt=dt_local,
            url="https://www.bls.gov/schedule/",
        ))
    return events

def fetch_bea_schedule(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.bea.gov/news/schedule"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    events: List[Event] = []

    # BEA schedule is a table-ish page. We'll parse rows that contain month/day + time + title.
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]
    # We'll look for patterns: MonthName Day + time + title, rough heuristic.
    month_names = "(January|February|March|April|May|June|July|August|September|October|November|December)"
    for i in range(len(lines) - 2):
        if re.match(rf"^{month_names}\s+\d{{1,2}}$", lines[i]):
            d = lines[i]
            t = lines[i+1]
            title = lines[i+3] if i+3 < len(lines) else ""
            if not re.search(r"\d", t):
                continue
            try:
                dt = dtparse(f"{d} {datetime.now().year} {t}", fuzzy=True)
            except Exception:
                continue
            # BEA times are ET
            dt = dt.replace(tzinfo=tz.gettz("America/New_York"))
            dt_local = dt.astimezone(tz_local)
            if start <= dt_local <= end:
                if title:
                    events.append(Event(dt_local=dt_local, currency="USD", title=title, source="BEA", url=url))
    return events

def fetch_fed_fomc_calendar(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    events: List[Event] = []

    # Parse date ranges like "January 28-29" etc. We'll capture month + day(-day)
    month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"^({month_names})\s+(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?$")
    year = datetime.now().year

    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        mon, d1, d2 = m.group(1), int(m.group(2)), m.group(3)
        d2i = int(d2) if d2 else d1
        # Use the *second day* as "decision day" at 20:00 CET? Actually statement 2pm ET.
        # We'll set at 20:00 Warsaw as a rough placeholder; user sees date which matters most.
        # Better: map 14:00 ET -> local.
        dt_et = dtparse(f"{mon} {d2i} {year} 14:00", fuzzy=True).replace(tzinfo=tz.gettz("America/New_York"))
        dt_local = dt_et.astimezone(tz_local)

        if start <= dt_local <= end:
            events.append(Event(dt_local=dt_local, currency="USD", title="FOMC rate decision (scheduled)", source="FED", url=url))
    return events

def fetch_ecb_gc_calendar(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    events: List[Event] = []
    # Dates are usually in dd/mm/yyyy format at start of list items
    text = soup.get_text("\n")
    for line in [normalize_space(x) for x in text.split("\n") if normalize_space(x)]:
        if re.match(r"^\d{2}/\d{2}/\d{4}", line):
            # "09/09/2026: Governing Council ... (Day 1)"
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            dstr, title = parts[0], normalize_space(parts[1])
            try:
                dt = dtparse(dstr, dayfirst=True).replace(tzinfo=tz.gettz("Europe/Brussels"))
            except Exception:
                continue
            # Time unknown; assume 12:00 CET
            dt = dt.replace(hour=12, minute=0, second=0)
            dt_local = dt.astimezone(tz_local)
            if start <= dt_local <= end and ("monetary policy" in title.lower()):
                events.append(Event(dt_local=dt_local, currency="EUR", title="ECB monetary policy meeting", source="ECB", url=url))
    return events

def fetch_ons_release_calendar(tz_local, start: datetime, end: datetime) -> List[Event]:
    """
    UK ONS release calendar (HTML list). We'll filter by keywords in config later.
    """
    url = "https://www.ons.gov.uk/releasecalendar"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    events: List[Event] = []
    # Items contain "Release date: 20 February 2026 7:00am"
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    for i, line in enumerate(lines):
        if line.lower().startswith("release date:"):
            date_part = line.split(":", 1)[1].strip()
            # title is previous line typically
            title = lines[i-1] if i > 0 else "ONS release"
            try:
                dt = dtparse(date_part, dayfirst=True, fuzzy=True)
            except Exception:
                continue
            # ONS release times are UK time
            dt = dt.replace(tzinfo=tz.gettz("Europe/London"))
            dt_local = dt.astimezone(tz_local)
            if start <= dt_local <= end:
                events.append(Event(dt_local=dt_local, currency="GBP", title=title, source="ONS", url=url))
    return events

def fetch_boc_schedule(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    events: List[Event] = []
    # Expect lines like "January 28 Interest rate announcement and Monetary Policy Report"
    month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"^({month_names})\s+(\d{{1,2}})\s+(Interest rate announcement.*)$")
    year = datetime.now().year
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        mon, day, title = m.group(1), int(m.group(2)), m.group(3)
        dt_et = dtparse(f"{mon} {day} {year} 09:45", fuzzy=True).replace(tzinfo=tz.gettz("America/Toronto"))
        dt_local = dt_et.astimezone(tz_local)
        if start <= dt_local <= end:
            events.append(Event(dt_local=dt_local, currency="CAD", title=title, source="BoC", url=url))
    return events

def fetch_boj_mpm_schedule(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    events: List[Event] = []
    # BOJ page includes dates like "January 22-23" etc under 2026 section.
    month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"^({month_names})\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})$")
    year = datetime.now().year
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        mon, d1, d2 = m.group(1), int(m.group(2)), int(m.group(3))
        # Decision day typically second day; time not fixed. Use 12:00 Tokyo.
        dt_tokyo = dtparse(f"{mon} {d2} {year} 12:00", fuzzy=True).replace(tzinfo=tz.gettz("Asia/Tokyo"))
        dt_local = dt_tokyo.astimezone(tz_local)
        if start <= dt_local <= end:
            events.append(Event(dt_local=dt_local, currency="JPY", title="BoJ monetary policy meeting (scheduled)", source="BoJ", url=url))
    return events

def fetch_snb_mpa_schedule(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.snb.ch/en/services-events/digital-services/event-schedule"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    events: List[Event] = []
    # Lines like "19.03.2026 09:30 Monetary policy assessment of 19 March 2026 (press release)"
    pat = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+(Monetary policy assessment.*)$", re.IGNORECASE)
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        dstr, tstr, title = m.group(1), m.group(2), normalize_space(m.group(3))
        try:
            dt = dtparse(f"{dstr} {tstr}", dayfirst=True).replace(tzinfo=tz.gettz("Europe/Zurich"))
        except Exception:
            continue
        dt_local = dt.astimezone(tz_local)
        if start <= dt_local <= end:
            events.append(Event(dt_local=dt_local, currency="CHF", title=title, source="SNB", url=url))
    return events

def fetch_rba_mpd_schedule(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.rba.gov.au/schedules-events/board-meeting-schedules.html"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    events: List[Event] = []
    # Rows like "February 2–3 February" etc; keep it simple: capture "Month 2–3 Month"
    month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"^({month_names})\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+({month_names})$", re.IGNORECASE)
    year = datetime.now().year
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        mon1, d1, d2, mon2 = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        # Decision day: second day at 14:30 Sydney (approx time for decision statement on their calendar page)
        dt_syd = dtparse(f"{mon2} {d2} {year} 14:30", fuzzy=True).replace(tzinfo=tz.gettz("Australia/Sydney"))
        dt_local = dt_syd.astimezone(tz_local)
        if start <= dt_local <= end:
            events.append(Event(dt_local=dt_local, currency="AUD", title="RBA Monetary Policy Board decision (scheduled)", source="RBA", url=url))
    return events

def fetch_rbnz_ocr_schedule(tz_local, start: datetime, end: datetime) -> List[Event]:
    url = "https://www.rbnz.govt.nz/news-and-events/how-we-release-information/ocr-decision-dates-and-financial-stability-report-dates-to-feb-2028"
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_space(x) for x in text.split("\n") if normalize_space(x)]

    events: List[Event] = []
    # Lines like "8 April  Monetary Policy Review and OCR"
    month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"^(\d{{1,2}})\s+({month_names})\s+(Monetary Policy .* OCR)$", re.IGNORECASE)
    year = datetime.now().year
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        day, mon, title = int(m.group(1)), m.group(2), normalize_space(m.group(3))
        # OCR announcements are typically 14:00 NZT; set 14:00 Auckland
        dt_nz = dtparse(f"{day} {mon} {year} 14:00", fuzzy=True).replace(tzinfo=tz.gettz("Pacific/Auckland"))
        dt_local = dt_nz.astimezone(tz_local)
        if start <= dt_local <= end:
            events.append(Event(dt_local=dt_local, currency="NZD", title=title, source="RBNZ", url=url))
    return events

# ----------------------------
# Telegram sender
# ----------------------------

def send_telegram_messages(token: str, chat_id: str, messages: List[str]) -> None:
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    for msg in messages:
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        r = requests.post(api, json=payload, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Telegram error: {r.status_code} {r.text}")

# ----------------------------
# Formatting
# ----------------------------

def fmt_header(now_local: datetime, start: datetime, end: datetime, extra_tags: List[str]) -> str:
    # ISO week range label
    return (
        f"📅 <b>Kalendarz makro (HIGH)</b>\n"
        f"Zakres: <b>{start.date().isoformat()}</b> → <b>{end.date().isoformat()}</b>\n"
        f"Strefa: {now_local.tzinfo}\n"
        f"{' '.join(extra_tags)}\n"
    )

def fmt_events(events: List[Event]) -> str:
    # group by date then currency
    events = sorted(events, key=lambda e: (e.dt_local.date(), e.dt_local.time(), e.currency, e.title))
    out = []
    current_day = None
    for ev in events:
        d = ev.dt_local.date()
        if d != current_day:
            if current_day is not None:
                out.append("")
            out.append(f"📌 <b>{d.strftime('%A')} {d.isoformat()}</b>")
            current_day = d
        hhmm = ev.dt_local.strftime("%H:%M")
        out.append(f"• <b>{hhmm}</b> [{ev.currency}] {ev.title} <i>({ev.source})</i>")
    return "\n".join(out) if out else "Brak wydarzeń spełniających filtr w tym tygodniu."

def build_message(now_local: datetime, start: datetime, end: datetime, events: List[Event], extra_tags: List[str]) -> str:
    return fmt_header(now_local, start, end, extra_tags) + "\n" + fmt_events(events)

# ----------------------------
# Main
# ----------------------------

def main() -> int:
    cfg = load_config()
    tz_local = get_tz(cfg["timezone"])

    now_local = datetime.now(tz=tz_local)
    start, end = week_window(now_local, bool(cfg.get("schedule", {}).get("saturday_next_week", True)))

    sources_cfg = cfg.get("sources", {})
    all_events: List[Event] = []

    if sources_cfg.get("bls_selected_releases", True):
        all_events += fetch_bls_selected_releases(tz_local, start, end)
    if sources_cfg.get("bea_schedule", True):
        all_events += fetch_bea_schedule(tz_local, start, end)
    if sources_cfg.get("fed_fomc_calendar", True):
        all_events += fetch_fed_fomc_calendar(tz_local, start, end)
    if sources_cfg.get("ecb_gc_calendar", True):
        all_events += fetch_ecb_gc_calendar(tz_local, start, end)
    if sources_cfg.get("ons_release_calendar", True):
        all_events += fetch_ons_release_calendar(tz_local, start, end)
    if sources_cfg.get("boc_schedule", True):
        all_events += fetch_boc_schedule(tz_local, start, end)
    if sources_cfg.get("boj_schedule", True):
        all_events += fetch_boj_mpm_schedule(tz_local, start, end)
    if sources_cfg.get("snb_schedule", True):
        all_events += fetch_snb_mpa_schedule(tz_local, start, end)
    if sources_cfg.get("rba_schedule", True):
        all_events += fetch_rba_mpd_schedule(tz_local, start, end)
    if sources_cfg.get("rbnz_schedule", True):
        all_events += fetch_rbnz_ocr_schedule(tz_local, start, end)

    # Apply HIGH filter
    currencies = set(cfg.get("filters", {}).get("currencies", []))
    high_keywords = cfg.get("high_keywords", {})
    filtered: List[Event] = []
    for ev in all_events:
        if currencies and ev.currency not in currencies:
            continue
        if match_high(ev.title, ev.currency, high_keywords):
            filtered.append(ev)

    # Deduplicate by (date,time,currency,title)
    uniq = {}
    for ev in filtered:
        key = (ev.dt_local.isoformat(timespec="minutes"), ev.currency, ev.title.lower())
        if key not in uniq:
            uniq[key] = ev
    filtered = list(uniq.values())

    # Build message and send
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID") or cfg.get("telegram", {}).get("chat_id")
    if not token:
        raise RuntimeError("Brak TG_BOT_TOKEN (ustaw w GitHub Secrets).")
    if not chat_id:
        raise RuntimeError("Brak TG_CHAT_ID (ustaw w GitHub Secrets).")

    max_len = int(cfg.get("telegram", {}).get("max_len", 3900))
    extra_tags = cfg.get("filters", {}).get("extra_tags", [])

    msg = build_message(now_local, start, end, filtered, extra_tags)
    chunks = split_telegram(msg, max_len)
    send_telegram_messages(token, chat_id, chunks)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
