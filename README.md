# Telegram Makro Kalendarz (HIGH) — v6

Ten projekt publikuje 1 post dziennie na Twoim publicznym kanale Telegram:
- zakres: **dziś → koniec tygodnia (niedziela)**,
- w sobotę: automatycznie **następny tydzień** (poniedziałek→niedziela),
- filtr: **HIGH** na podstawie słów kluczowych (bo darmowe oficjalne źródła rzadko mają gotowe "impact"),
- waluty: USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD,
- dodatkowe tagi: #XAU #XAG #NAS100,
- jeśli post jest za długi — automatycznie dzieli na części.

## Dlaczego były błędy 403?
Niektóre strony (np. część instytucji) potrafią blokować automatyczne pobieranie z serwerów GitHub (403).
W tej wersji bot **nigdy nie wywala całego działania**: zablokowane źródło jest **pomijane**, a post i tak zostaje wysłany.

---

## Krok po kroku: uruchomienie (bez znajomości programowania)

### A) Telegram — bot i kanał
1. Utwórz **kanał publiczny** w Telegram i nadaj mu nazwę użytkownika, np. `@TwojKanal`.
2. W Telegram wpisz: **@BotFather**
3. Komenda: `/newbot`
4. Ustaw nazwę i username bota.
5. BotFather pokaże Ci **TOKEN** — skopiuj go.
6. Wejdź w ustawienia kanału → **Administrators** → **Add Admin** → wybierz swojego bota.
7. Nadaj mu uprawnienie **Post messages** (publikowanie postów).

### B) GitHub — repo
1. Wejdź na GitHub i utwórz nowe repo (public lub private).
2. Wejdź do repo → **Add file → Upload files**.
3. Wgraj **wszystkie pliki** z tej paczki (rozpakuj ZIP i wrzuć zawartość).
4. Kliknij **Commit changes**.

### C) GitHub — sekrety (token i kanał)
1. Repo → **Settings**
2. **Secrets and variables → Actions**
3. Kliknij **New repository secret** i dodaj:
   - `TG_BOT_TOKEN` = token z BotFather
   - `TG_CHAT_ID` = `@TwojKanal` (dokładnie z @)

### D) Test ręczny (uruchomienie)
1. Repo → zakładka **Actions**
2. Po lewej wybierz: **Telegram Macro Calendar**
3. Kliknij **Run workflow** → **Run workflow**
4. Wejdź w wykonanie (run) i sprawdź logi.
5. Sprawdź, czy na kanale pojawił się post.

---

## Jeśli nic nie publikuje na kanale
Najczęstsze przyczyny:
- bot nie jest adminem kanału,
- bot nie ma prawa „Post messages”,
- `TG_CHAT_ID` jest bez `@` albo ma literówkę,
- kanał jest prywatny (ma brak @username).

---

## Dalsze ulepszenia
Jeśli chcesz bardziej „TradingView-like” listę HIGH (CPI/NFP/GDP itp. z godzinami i liczbowymi prognozami),
to do tego zwykle potrzebne są dane licencjonowane. W tej wersji trzymamy się darmowych źródeł + best‑effort.
