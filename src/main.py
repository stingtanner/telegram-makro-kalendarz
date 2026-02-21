import os
import math
import requests
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from dateutil import parser as dtparser

WARSAW = ZoneInfo("Europe/Warsaw")

CURRENCIES = {"USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD"}
EXTRA_TAGS = "#XAU #XAG #NAS100"

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN","").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID","").strip()
FMP_API_KEY = os.environ.get("FMP_API_KEY","").strip()

TELEGRAM_LIMIT = 3900  # bezpieczny limit (Telegram ma ~4096)

FLAGS = {
    "USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","JPY":"🇯🇵","CHF":"🇨🇭","CAD":"🇨🇦","AUD":"🇦🇺","NZD":"🇳🇿"
}

def warsaw_today() -> date:
    return datetime.now(WARSAW).date()

def week_window(today: date):
    wd = today.weekday()  # Mon=0..Sun=6
    if wd == 5:  # Saturday -> next week
        start = today + timedelta(days=2)
        end = start + timedelta(days=6)
    else:
        start = today
        end = today + timedelta(days=(6 - wd))
    return start, end

def http_get_json(url: str, params: dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TelegramMacroCalendar/1.0; +https://github.com/)",
        "Accept": "application/json",
    }
    r = requests.get(url, params=params, headers=headers, timeout=30)
    # Nie wypisujemy URL z tokenami w błędach
    if r.status_code >= 400:
        raise requests.HTTPError(f"HTTP {r.status_code} from data provider", response=r)
    return r.json()

def normalize_impact(ev: dict) -> str:
    # FMP może używać różnych nazw pól w zależności od wersji.
    for k in ("impact","Impact","importance","Importance","volatility","Volatility"):
        if k in ev and ev[k] is not None:
            v = str(ev[k]).strip().lower()
            if v in {"high","3","high impact","high-impact"}: return "high"
            if v in {"medium","2"}: return "medium"
            if v in {"low","1"}: return "low"
    # Czasem brak – wtedy nie uznajemy za HIGH
    return "unknown"

def parse_datetime(ev: dict) -> datetime | None:
    # próbujemy różnych pól
    candidates = []
    for k in ("date","Date","datetime","Datetime","publishedDate","PublishedDate"):
        if k in ev and ev[k]:
            candidates.append(str(ev[k]))
    # czasem osobno: date + time
    d = ev.get("date") or ev.get("Date")
    t = ev.get("time") or ev.get("Time")
    if d and t:
        candidates.insert(0, f"{d} {t}")
    for s in candidates:
        try:
            dt = dtparser.parse(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=WARSAW)
            else:
                dt = dt.astimezone(WARSAW)
            return dt
        except Exception:
            continue
    return None

def extract_currency(ev: dict) -> str:
    for k in ("currency","Currency"):
        if k in ev and ev[k]:
            return str(ev[k]).upper().strip()
    # czasem "country" -> mapowanie? zostawiamy puste
    return ""

def extract_event_name(ev: dict) -> str:
    for k in ("event","Event","title","Title","name","Name","indicator","Indicator"):
        if k in ev and ev[k]:
            return str(ev[k]).strip()
    return "Wydarzenie"

def fetch_fmp_calendar(start: date, end: date) -> list[dict]:
    # dokumentacja: https://financialmodelingprep.com/stable/economic-calendar
    url = "https://financialmodelingprep.com/stable/economic-calendar"
    params = {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "apikey": FMP_API_KEY,
    }
    data = http_get_json(url, params=params)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=30)
    if r.status_code >= 400:
        raise requests.HTTPError(f"Telegram HTTP {r.status_code}", response=r)

def split_message(full: str) -> list[str]:
    if len(full) <= TELEGRAM_LIMIT:
        return [full]
    parts = []
    buf = ""
    for line in full.splitlines(True):
        if len(buf) + len(line) > TELEGRAM_LIMIT:
            parts.append(buf.rstrip())
            buf = ""
        buf += line
    if buf.strip():
        parts.append(buf.rstrip())
    # numeracja części
    if len(parts) > 1:
        total = len(parts)
        parts = [f"{p}\n\n({i+1}/{total})" for i,p in enumerate(parts)]
    return parts

def build_message(start: date, end: date, events: list[dict]) -> str:
    header = (
        f"📅 Kalendarz makro (HIGH) — {start.isoformat()} → {end.isoformat()} (Warszawa)\n"
        f"Waluty: {', '.join(sorted(CURRENCIES))}\n"
        f"Dodatkowo: {EXTRA_TAGS}\n"
        f"Źródło: FMP Economic Calendar (API)\n\n"
    )

    if not events:
        return header + "Brak danych HIGH do pokazania w tym zakresie.\n\n#forex #kalendarz #highimpact " + EXTRA_TAGS.replace(" ", " ")

    # sortuj po czasie
    rows = []
    for ev in events:
        cur = extract_currency(ev)
        if cur not in CURRENCIES:
            continue
        if normalize_impact(ev) != "high":
            continue
        dt = parse_datetime(ev)
        if not dt:
            continue
        if not (start <= dt.date() <= end):
            continue
        name = extract_event_name(ev)
        actual = ev.get("actual") or ev.get("Actual")
        forecast = ev.get("forecast") or ev.get("Forecast")
        previous = ev.get("previous") or ev.get("Previous")
        rows.append((dt, cur, name, actual, forecast, previous))

    rows.sort(key=lambda x: x[0])

    if not rows:
        return header + "Brak danych HIGH do pokazania w tym zakresie.\n\n#forex #kalendarz #highimpact " + EXTRA_TAGS.replace(" ", " ")

    out = [header]
    current_day = None
    for dt, cur, name, actual, forecast, previous in rows:
        if dt.date() != current_day:
            current_day = dt.date()
            out.append(f"🗓 {current_day.isoformat()} ({current_day.strftime('%a')})")
        flag = FLAGS.get(cur, "🏳️")
        line = f"• ⏰ {dt.strftime('%H:%M')}  {flag} {cur} — {name}"
        extras = []
        if actual not in (None,"","N/A"): extras.append(f"Actual: {actual}")
        if forecast not in (None,"","N/A"): extras.append(f"Forecast: {forecast}")
        if previous not in (None,"","N/A"): extras.append(f"Previous: {previous}")
        if extras:
            line += "\n  " + " | ".join(extras)
        out.append(line)
        out.append("")  # pusta linia

    out.append(f"#forex #kalendarz #highimpact {EXTRA_TAGS.replace(' ', ' ')}")
    return "\n".join(out).strip()

def main():
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        raise SystemExit("Brak TG_BOT_TOKEN lub TG_CHAT_ID w sekretach GitHub.")
    if not FMP_API_KEY:
        raise SystemExit("Brak FMP_API_KEY w sekretach GitHub.")

    today = warsaw_today()
    start, end = week_window(today)

    try:
        data = fetch_fmp_calendar(start, end)
        msg = build_message(start, end, data)
    except Exception as e:
        # bez ujawniania tokenów
        msg = (
            f"📅 Kalendarz makro (HIGH) — {start.isoformat()} → {end.isoformat()} (Warszawa)\n"
            f"Waluty: {', '.join(sorted(CURRENCIES))}\n"
            f"Dodatkowo: {EXTRA_TAGS}\n\n"
            f"❌ Błąd pobierania danych z FMP.\n"
            f"Szczegóły: {type(e).__name__}: {str(e)}\n\n"
            f"#forex #kalendarz #highimpact {EXTRA_TAGS.replace(' ', ' ')}"
        )

    for part in split_message(msg):
        tg_send(part)

if __name__ == "__main__":
    main()
