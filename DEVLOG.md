# DEVLOG (v3)

## v3 – ZMiana źródeł na darmowe (2026-02-21)
ZROBIONE:
- Usunięto zależność od TradingEconomics (brak darmowego planu).
- Źródła zastąpione darmowymi, oficjalnymi stronami instytucji:
  - BLS / BEA / FED (USA)
  - ECB (EUR)
  - ONS (GBP)
  - Bank of Canada (CAD)
  - Bank of Japan (JPY)
  - SNB (CHF)
  - RBA (AUD)
  - RBNZ (NZD)
- Filtr „HIGH” realizowany przez słowa kluczowe w `config.yaml`.
- Automatyczne dzielenie posta, gdy przekracza limit Telegrama.
- Harmonogram: codziennie, a w sobotę przełączenie zakresu na przyszły tydzień.

DO ZROBIENIA (opcjonalnie):
- Dodać więcej „HIGH” publikacji dla EUR/GBP (np. inflacja/GDP) z dodatkowych oficjalnych źródeł (gdy będziesz chciał).
- Lepsza obsługa zmian godzin publikacji (np. w sytuacji przesunięć przez święta).
