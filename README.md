# Telegram – Kalendarz makro (HIGH) dla Forex (v5)

Cel: publiczny kanał Telegram, który **raz dziennie** publikuje listę **najważniejszych (HIGH)** wydarzeń makro **od dziś do końca bieżącego tygodnia**.
W sobotę (wg ustawień) automatycznie przełącza zakres na **następny tydzień**.

> Zmieniliśmy źródła na **darmowe, oficjalne strony instytucji** (bez TradingEconomics).

## Co jest publikowane
- Tylko wydarzenia oznaczone przez nas jako **HIGH** (filtr słów kluczowych w `config.yaml`)
- Tylko główne waluty: **USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD**
- Dodatkowe tagi w nagłówku posta: **Złoto / Srebro / NASDAQ** (`#XAU #XAG #NAS100 ...`)

## Skąd bierzemy dane (darmowe źródła)
Program pobiera i filtruje wydarzenia z oficjalnych stron:
- USA: BLS (wybrane publikacje), BEA (harmonogram), FED (kalendarz FOMC)  
- EUR: ECB (kalendarz posiedzeń Rady Prezesów – monetary policy meetings)
- UK: ONS release calendar
- CAD: Bank of Canada – schedule of interest rate announcements
- JPY: Bank of Japan – Monetary Policy Meetings schedule
- CHF: SNB – event schedule (monetary policy assessment)
- AUD: RBA – board meeting schedules
- NZD: RBNZ – OCR decision dates

Uwaga: to są **terminy publikacji / posiedzeń**. Nie pobieramy „actual/forecast/previous” (to zwykle jest licencjonowane przez serwisy komercyjne).

## Jak uruchomić (KROK PO KROKU, bez programowania)

### Krok 1: Załóż publiczny kanał Telegram
1. Telegram → **Utwórz kanał**
2. Wybierz **Publiczny**
3. Ustaw **@nazwakanału** (to będzie Twój publiczny `chat_id`)

### Krok 2: Zrób bota w Telegram (BotFather)
1. W Telegram wyszukaj: **@BotFather**
2. Kliknij **Start**
3. Wyślij komendę: `/newbot`
4. Nadaj nazwę i username bota (np. `KalendarzMakroBot`)
5. BotFather poda Ci **TOKEN** (ważne!)

### Krok 3: Dodaj bota jako admin kanału
1. Wejdź w kanał → **Zarządzaj kanałem** → **Administratorzy**
2. Dodaj swojego bota i nadaj uprawnienia:
   - **Post messages** (publikowanie)
   - (opcjonalnie) **Edit messages** (nie jest wymagane)

### Krok 4: Zrób repozytorium na GitHub i wgraj pliki
1. Wejdź na GitHub → **New repository**
2. Nazwa np. `telegram-makro-kalendarz`
3. Zaznacz **Public** (może być Public albo Private – działa tak samo)
4. Kliknij **Create repository**
5. Wgraj wszystkie pliki z tej paczki ZIP do repo (Upload files)

### Krok 5: Ustaw sekrety (TOKEN i kanał)
1. Repo na GitHub → **Settings**
2. Po lewej: **Secrets and variables** → **Actions**
3. Kliknij **New repository secret** i dodaj:
   - `TG_BOT_TOKEN` = token z BotFather
   - `TG_CHAT_ID` = `@TwojKanal` (dokładnie taki jak publiczna nazwa kanału)

### Krok 6: Włącz GitHub Actions i przetestuj ręcznie
1. Repo → zakładka **Actions**
2. Jeśli GitHub poprosi o włączenie workflow – włącz.
3. Wejdź w workflow: **Daily economic calendar (HIGH) -> Telegram**
4. Kliknij **Run workflow** → uruchom ręcznie
5. Sprawdź kanał Telegram – powinien pojawić się post.

## Harmonogram
Workflow jest ustawiony na uruchamianie w okolicach północy Warszawy:
- `.github/workflows/daily.yml`

GitHub cron działa w UTC, dlatego są **dwa** wywołania (na czas letni/zimowy).

## Jak zmienić co jest „HIGH”
Otwórz `config.yaml` i edytuj sekcję:
- `high_keywords` (dla każdej waluty lista słów kluczowych)
- `filters.currencies` (lista walut)
- `filters.extra_tags` (tagi w nagłówku)

## Jeśli post jest za długi
Program automatycznie dzieli wiadomość na kilka postów (limit ustawisz w `telegram.max_len`).

## Najczęstsze problemy
- **Brak posta na kanale**: bot nie jest adminem albo nie ma uprawnienia „Post messages”.
- **Błąd TG_CHAT_ID**: dla publicznego kanału wpisz dokładnie `@nazwa`.
- **GitHub Actions nie działa**: repo → Actions → włącz workflow.


## Zmiany v5
- Naprawa źródła BLS: zamiast scrapowania HTML (czasem 403 w GitHub Actions) używany jest oficjalny feed iCalendar (.ics): https://www.bls.gov/schedule/news_release/bls.ics
