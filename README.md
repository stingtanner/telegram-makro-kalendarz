# Forex Economic Calendar → Telegram (PUBLIC) — v8

Ta wersja jest **stabilna i "profesjonalna"**, bo **nie scrapuje stron HTML** instytucji (które często blokują GitHub Actions kodem 403), tylko korzysta z **Economic Calendar API**.

## Co robi bot
- Publikuje na Twoim **publicznym kanale Telegram** 1 post dziennie.
- Post zawiera **tylko wydarzenia HIGH impact**.
- Tylko główne waluty: **AUD, CAD, CHF, EUR, GBP, JPY, NZD, USD**.
- Dodatkowo dopisuje tagi: **#XAU #XAG #NAS100** (złoto, srebro, NASDAQ).
- Zakres dat:
  - **codziennie:** od dziś do końca tygodnia (niedziela)
  - **w sobotę:** publikuje wydarzenia na **kolejny tydzień** (poniedziałek→niedziela)
- Jeśli post jest za długi, automatycznie dzieli go na kilka wiadomości.

## Źródło danych
- Finnhub — Economic Calendar API (free tier).

---

# Instrukcja krok po kroku (dla początkujących)

## A) Telegram: kanał i bot
1. **Utwórz kanał publiczny** w Telegramie i ustaw jego nazwę użytkownika (np. `@ForexKalendarzPL`).
2. Wejdź na Telegramie w **@BotFather**
   - wpisz: `/newbot`
   - nadaj nazwę i username bota
   - na końcu dostaniesz **TOKEN** (ciąg znaków) → skopiuj go.
3. Wejdź w ustawienia kanału → **Administratorzy** → **Dodaj administratora**
   - dodaj swojego bota
   - zaznacz uprawnienie **Publikowanie wiadomości** (Post messages).

## B) Finnhub: darmowy token API
1. Załóż konto na Finnhub.
2. W panelu Finnhub skopiuj swój **API Token**.

## C) GitHub: wrzucenie plików
1. Utwórz repozytorium na GitHub (może być publiczne lub prywatne).
2. W repo kliknij: **Add file → Upload files**
3. Wgraj wszystkie pliki z tej paczki (folder `.github`, folder `src`, pliki `README.md`, `requirements.txt`).
4. Kliknij **Commit changes**.

## D) GitHub: dodanie sekretów
1. Wejdź w repo → **Settings**
2. Po lewej: **Secrets and variables → Actions**
3. Kliknij **New repository secret** i dodaj 3 sekrety:

- `TG_BOT_TOKEN` → wklej token z BotFather
- `TG_CHAT_ID` → wpisz nazwę kanału, np. `@ForexKalendarzPL`
- `FINNHUB_TOKEN` → wklej token z Finnhub

## E) Test ręczny (ważne!)
1. Wejdź w repo → zakładka **Actions**
2. Kliknij workflow: **Telegram Macro Calendar**
3. Kliknij **Run workflow** → ponownie **Run workflow**
4. Wejdź na kanał Telegram i sprawdź czy pojawił się post.

## F) Automatyczna publikacja o północy
Workflow jest ustawiony na uruchamianie codziennie (cron). GitHub liczy czas w UTC, ale ustawiliśmy godzinę tak, żeby była **w okolicach północy w Polsce**.

---

# Najczęstsze problemy

## 1) Brak wiadomości na kanale
- sprawdź czy bot jest administratorem i ma **Post messages**
- sprawdź `TG_CHAT_ID` (musi zaczynać się od `@`)

## 2) Bot publikuje komunikat o błędzie Finnhub
- sprawdź czy secret `FINNHUB_TOKEN` jest poprawny
- jeśli Finnhub daje limit (free tier), to odpalaj testy rzadziej

---

Powodzenia 🚀
