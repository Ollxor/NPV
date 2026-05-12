# NPV Omvärldsbevakning

Automatiserad bevakning av psykedelisk forskning och nyheter för [Nätverket för Psykedelisk Vetenskap](https://npv.se). Systemet söker dagligen efter relevanta artiklar och veckovis efter kandidater till NPV:s uppsatspris, genererar förslag på Facebook-inlägg med Claude och postar till Slack för redaktionell granskning.

## Daglig forskningsbevakning

Kör **varje dag kl 07:00 CET**. Hämtar nya artiklar utan tidsbegränsning — fokus är på det senaste från PubMed, Semantic Scholar, Psychedelic Alpha och DiVA.

**Reaktioner i Slack:**
- ✅ publicerad · 👍 bra, posta snart · 👎 ej relevant

## Veckovis uppsatsprisbevakning

Kör **varje måndag kl 07:00 CET**. Söker igenom DiVA och SwePub efter nya kandidat- och masteruppsatser inom psykedelisk vetenskap.

**Sökperiod:** Endast uppsatser publicerade under **innevarande kalenderår** inkluderas. Priset för 2026 års uppsatser delas ut under våren 2027 — sökningen körs löpande under hela 2026 och fångar upp nya uppsatser allteftersom de publiceras.

Nästa prisår (2027) börjar systemet automatiskt söka efter 2027 års uppsatser utan att något behöver ändras.

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
  fetch_theses.py         # Hämtar uppsatser (filtrerat på innevarande år)
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
