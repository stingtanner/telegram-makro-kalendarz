# Telegram Makro Kalendarz (HIGH) — v9 (FMP)

Ta wersja używa **Financial Modeling Prep (FMP) – Economic Calendar API** zamiast Finnhub/TradingEconomics.
Działa z darmowym planem (limit dzienny) i jest stabilna na GitHub Actions.

## Co publikuje
- tylko **HIGH impact**
- tylko waluty: **USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD**
- dodatkowe tagi w nagłówku: **#XAU #XAG #NAS100**
- harmonogram:
  - codziennie: zakres **od dziś do niedzieli**
  - w sobotę: zakres **kolejny tydzień (pon–nd)**
- automatyczne dzielenie posta, jeśli przekracza limit Telegrama

## Krok po kroku (bez wiedzy technicznej)

### A) Telegram – bot i kanał
1. W Telegramie utwórz **kanał publiczny** i ustaw nazwę użytkownika, np. `@TwojKanal`.
2. Otwórz czat z **@BotFather** → wpisz `/newbot` → nadaj nazwę i username bota.
3. Skopiuj token bota (ciąg znaków typu `123456:ABC...`).
4. Wejdź w ustawienia kanału → **Administrators** → **Add Admin** → wybierz swojego bota → pozwól mu **Post messages**.

### B) FMP – darmowy klucz API
1. Załóż konto w Financial Modeling Prep.
2. Skopiuj swój **API Key** z panelu (FMP).

### C) GitHub – wgranie plików
1. Wejdź do repo na GitHub → zakładka **Code**.
2. Kliknij **Add file → Upload files**.
3. Wgraj (przeciągnij) całą zawartość tej paczki ZIP.
4. Kliknij **Commit changes**.

### D) GitHub – ustawienie sekretów
1. Repo → **Settings**
2. **Secrets and variables → Actions**
3. Kliknij **New repository secret** i dodaj 3 sekrety:

- `TG_BOT_TOKEN` = token z BotFather
- `TG_CHAT_ID` = nazwa kanału, np. `@TwojKanal`
- `FMP_API_KEY` = klucz API z FMP

### E) Test ręczny (żeby sprawdzić, że działa)
1. Repo → zakładka **Actions**
2. Kliknij workflow **Telegram Macro Calendar**
3. Kliknij **Run workflow** → **Run workflow**
4. Sprawdź post na kanale.

## Ważne bezpieczeństwo
Nigdy nie wklejaj tokenów w treści posta ani w publicznych plikach repo. Ta wersja nie wypisuje tokenów w błędach.
