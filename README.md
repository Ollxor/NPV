# NPV Omvärldsbevakning

Automatiserad bevakning av psykedelisk forskning och nyheter för [Nätverket för Psykedelisk Vetenskap](https://npv.se). Systemet söker dagligen efter relevanta artiklar och veckovis efter kandidater till NPV:s uppsatspris, genererar förslag på Facebook-inlägg med Claude och postar till Slack för redaktionell granskning.

## Daglig forskningsbevakning

Kör varje dag kl 07:00 CET. Hämtar nya artiklar från PubMed, Semantic Scholar, Psychedelic Alpha och DiVA, filtrerar med Claude och genererar ett förslag på Facebook-text per relevant artikel.

**Reaktioner i Slack:**
- ✅ publicerad · 👍 bra, posta snart · 👎 ej relevant

## Veckovis uppsatsprisbevakning

Kör varje måndag kl 07:00 CET. Söker igenom DiVA och SwePub efter nya kandidat- och masteruppsatser inom psykedelisk vetenskap som kan vara aktuella för NPV:s uppsatspris.

**Reaktioner i Slack:**
- 👍 Intressant kandidat · 👎 Ej relevant · 📬 Kandidat kontaktad · 📝 Ansökan inkommen

## Källor

- **PubMed** — via NCBI E-utilities API
- **Semantic Scholar** — öppet API
- **Psychedelic Alpha** — via RSS
- **DiVA** — svenska uppsatser och examensarbeten
- **SwePub** — svensk akademisk publicering (KB)

## Repo-struktur

```
.github/workflows/
  daily-scan.yml          # Daglig forskningsbevakning
  weekly-thesis-scan.yml  # Veckovis uppsatsprisbevakning
src/
  main.py                 # Entry point daglig sökning
  thesis_main.py          # Entry point uppsatsprisbevakning
  fetch_sources.py        # Hämtar forskningsartiklar
  fetch_theses.py         # Hämtar uppsatser
  filter_and_summarize.py # Relevansbedömning + FB-text
  filter_theses.py        # Relevansbedömning för uppsatspris
  post_to_slack.py        # Slack-integration
  seen_articles.py        # Deduplikering
data/
  seen.json               # Sedda forskningsartiklar
  seen_theses.json        # Sedda uppsatser
```

## AI-modell

Använder `claude-haiku-4-5-20251001`. Varje daglig körning kostar uppskattningsvis < 0,05 USD.
