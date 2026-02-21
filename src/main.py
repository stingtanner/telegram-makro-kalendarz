"""telegram-makro-kalendarz (v8)

PROFESJONALNA, stabilna wersja bez scrapowania stron.

Dlaczego tak:
- Serwisy instytucji (BLS, RBNZ, itd.) często blokują GitHub Actions (403).
- Żeby mieć kalendarz jak w TradingView (impact / lista publikacji), potrzebne jest źródło, które *udostępnia dane w formie API*.

Źródło danych (free tier): Finnhub Economic Calendar API.
- Endpoint: /api/v1/calendar/economic
- Zwraca m.in. currency, event, impact, date/time, actual/forecast/previous.

Wymagania:
- ustaw sekrety GitHub Actions:
  - TG_BOT_TOKEN
  - TG_CHAT_ID
  - FINNHUB_TOKEN

Tryb pracy:
- raz dziennie około północy (Warszawa) publikuje wydarzenia HIGH
  - dziś → niedziela
  - w sobotę: poniedziałek → niedziela kolejnego tygodnia

Uwaga:
- "Złoto/Srebro/NASDAQ" (XAU/XAG/NAS100) to nie waluty z kalendarza makro.
  Dodajemy je jako tagi w poście (tak jak prosiłeś), żeby łatwo filtrować kanał.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# -------------------- Konfiguracja --------------------

MAJOR_CCY = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD"]
EXTRA_TAGS = ["#XAU", "#XAG", "#NAS100"]

WARSAW_TZ_NAME = "Europe/Warsaw"

# Telegram limit to 4096 chars; keep margin.
TG_LIMIT = 3900

# Finnhub: best-effort retries (free tier)
HTTP_TIMEOUT = 30
HTTP_TRIES = 3

FLAG = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "JPY": "🇯🇵",
    "CHF": "🇨🇭",
    "CAD": "🇨🇦",
    "AUD": "🇦🇺",
    "NZD": "🇳🇿",
}


@dataclass
class CalEvent:
    d: date
    time_str: str  # as provided by API (often HH:MM)
    ccy: str
    impact: str
    event: str
    country: str
    actual: Optional[str]
    forecast: Optional[str]
    previous: Optional[str]


# -------------------- Time window --------------------


def warsaw_today() -> date:
    # Avoid extra dependencies; use system tz via environment where possible.
    # GitHub runners are UTC; we shift by Warsaw offset approximately using pytz is not allowed.
    # Instead, we rely on "cron" set near Warsaw midnight; and compute based on UTC date + 1h/2h.
    # For correctness, we allow overriding via env for testing.
    override = os.getenv("FORCE_TODAY")
    if override:
        return date.fromisoformat(override)

    # Compute Warsaw date by using zoneinfo if available (Python 3.11 has it).
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(WARSAW_TZ_NAME)).date()
    except Exception:
        # Fallback: approximate with UTC now + 1 hour (good enough for around midnight runs)
        return (datetime.utcnow() + timedelta(hours=1)).date()


def week_window(today: date) -> Tuple[date, date]:
    # weekday: Mon=0..Sun=6
    wd = today.weekday()
    if wd == 5:  # Saturday → next week
        start = today + timedelta(days=2)  # Monday
        end = start + timedelta(days=6)  # Sunday
    else:
        start = today
        end = today + timedelta(days=(6 - wd))
    return start, end


# -------------------- Finnhub API --------------------


def http_get_json(url: str, params: Dict[str, str]) -> Any:
    last_exc: Optional[Exception] = None
    for i in range(HTTP_TRIES):
        try:
            r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
            # Finnhub may rate limit (429). Backoff then retry.
            if r.status_code == 429:
                time.sleep(2.0 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            time.sleep(1.5 * (i + 1))
    raise last_exc  # type: ignore


def fetch_finnhub_calendar(start: date, end: date) -> List[CalEvent]:
    token = os.environ.get("FINNHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Brak FINNHUB_TOKEN. Dodaj go w GitHub: Settings → Secrets and variables → Actions."
        )

    url = "https://finnhub.io/api/v1/calendar/economic"
    data = http_get_json(
        url,
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "token": token,
        },
    )

    items = data.get("economicCalendar") or data.get("economicCalendar", [])
    if not isinstance(items, list):
        return []

    out: List[CalEvent] = []
    for it in items:
        try:
            ccy = (it.get("currency") or "").upper().strip()
            if ccy not in MAJOR_CCY:
                continue

            impact = (it.get("impact") or "").strip()
            # Finnhub usually returns "High"/"Medium"/"Low"
            if impact.lower() != "high":
                continue

            d_str = (it.get("date") or "").strip()
            if not d_str:
                continue
            d = date.fromisoformat(d_str)

            time_str = (it.get("time") or "").strip() or "--:--"
            event = (it.get("event") or "").strip() or "(brak nazwy)"
            country = (it.get("country") or "").strip()

            def _val(k: str) -> Optional[str]:
                v = it.get(k)
                if v is None:
                    return None
                s = str(v).strip()
                return s if s and s.lower() != "nan" else None

            out.append(
                CalEvent(
                    d=d,
                    time_str=time_str,
                    ccy=ccy,
                    impact=impact,
                    event=event,
                    country=country,
                    actual=_val("actual"),
                    forecast=_val("forecast"),
                    previous=_val("previous"),
                )
            )
        except Exception:
            continue

    # sort by date then time string
    out.sort(key=lambda e: (e.d, e.time_str, e.ccy, e.event))
    return out


# -------------------- Telegram --------------------


def tg_send(text: str) -> None:
    token = os.environ["TG_BOT_TOKEN"].strip()
    chat_id = os.environ["TG_CHAT_ID"].strip()
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

    def flush():
        nonlocal cur
        if cur:
            parts.append(cur)
            cur = ""

    # split by blank lines blocks
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        candidate = (cur + ("\n\n" if cur else "") + block)
        if len(candidate) <= limit:
            cur = candidate
        else:
            flush()
            if len(block) <= limit:
                cur = block
            else:
                # hard split long block
                for i in range(0, len(block), limit):
                    parts.append(block[i : i + limit])
    flush()
    return parts


# -------------------- Formatowanie --------------------


def format_post(start: date, end: date, events: List[CalEvent]) -> str:
    header = (
        f"📅 Kalendarz makro (HIGH) — {start.isoformat()} → {end.isoformat()} (Warszawa)\n"
        f"Waluty: {', '.join(MAJOR_CCY)}\n"
        f"Dodatkowo: {' '.join(EXTRA_TAGS)}\n"
        "Źródło: Finnhub Economic Calendar (free tier)."
    )

    if not events:
        return (
            header
            + "\n\nBrak wydarzeń HIGH w tym tygodniu dla wybranych walut.\n"
            + "\n#forex #kalendarz #highimpact "
            + " ".join(EXTRA_TAGS)
        )

    # group by date
    out: List[str] = [header]

    cur_day: Optional[date] = None
    for e in events:
        if cur_day != e.d:
            cur_day = e.d
            out.append(f"\n🗓 {cur_day.isoformat()}")

        flag = FLAG.get(e.ccy, "🏳️")
        line = f"• ⏰ {e.time_str}  {flag} {e.ccy} — {e.event}"
        if e.country:
            line += f" ({e.country})"

        extras: List[str] = []
        if e.actual is not None:
            extras.append(f"Actual: {e.actual}")
        if e.forecast is not None:
            extras.append(f"Forecast: {e.forecast}")
        if e.previous is not None:
            extras.append(f"Previous: {e.previous}")
        if extras:
            line += "\n  " + " | ".join(extras)

        out.append(line)

    out.append("\n#forex #kalendarz #highimpact " + " ".join(EXTRA_TAGS))
    return "\n".join(out).strip()


# -------------------- Main --------------------


def main() -> int:
    today = warsaw_today()
    start, end = week_window(today)

    try:
        events = fetch_finnhub_calendar(start, end)
    except Exception as e:
        # If API fails, still publish a short diagnostic (so you know it's alive)
        msg = (
            f"📅 Kalendarz makro (HIGH) — {start.isoformat()} → {end.isoformat()} (Warszawa)\n"
            f"Waluty: {', '.join(MAJOR_CCY)}\n"
            f"Dodatkowo: {' '.join(EXTRA_TAGS)}\n\n"
            "❌ Błąd pobierania danych z Finnhub.\n"
            f"Szczegóły: {type(e).__name__}: {e}\n\n"
            "#forex #kalendarz #highimpact "
            + " ".join(EXTRA_TAGS)
        )
        for part in split_messages(msg):
            tg_send(part)
        return 0

    post = format_post(start, end, events)
    for part in split_messages(post):
        tg_send(part)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
