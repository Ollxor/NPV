# NPV Omvärldsbevakning

Automatiserad bevakning av psykedelisk forskning och nyheter för [Nätverket för Psykedelisk Vetenskap](https://npv.se). Systemet hämtar dagligen nya artiklar från nio källor (Norden till EU-nivå), filtrerar och sammanfattar dem med Claude, och levererar resultatet på två spår:

1. **Internt i Slack** — svenska sammanfattningar och Facebook-textförslag för redaktionell granskning.
2. **Publikt på GitHub Pages** — ett flerspråkigt engelska/nordiska/baltiska webbflöde: **<https://ollxor.github.io/NPV/>**

## Daglig forskningsbevakning (Slack)

Kör **varje dag kl 06:00 UTC**. Hämtar nya artiklar från samtliga nio källor, filtrerar med Claude och postar relevanta artiklar till Slack med förslag på Facebook-text.

**Anmärkningsvärda fynd** (⚡) flaggas separat — fas 2b/3-resultat, myndighetsbeslut (FDA/EMA), publicering i toppjournaler (Nature, Science, NEJM, Lancet, JAMA, Cell, PNAS), stora RCT:er (n>200) eller nationella policyändringar får en egen rubrik i Slack-inlägget med en kort motivering.

**Reaktioner i Slack:**
- ✅ publicerad · 👍 bra, posta snart · 👎 ej relevant

## Engelskt webbflöde (GitHub Pages)

Kör **varje dag kl 06:30 UTC**, 30 minuter efter den svenska bevakningen (delar samma dagliga hämtning via cachen, se nedan). Publicerar ett rullande flöde (senaste 60 artiklarna) på <https://ollxor.github.io/NPV/> med:

- **9 språk** — engelska, svenska, norska, danska, finska, isländska, estniska, lettiska, litauiska. Sammanfattningar och "anmärkningsvärt"-motiveringar genereras och översätts i samma Claude-anrop.
- **Källfilter** — flikar för Alla / Akademiskt / Kliniska studier / Policy & nyheter.
- **Författare** synliga på varje artikelkort.
- **Veckovis och kvartalsvis analys** som egna flikar (se nedan).

## Veckovis sammanfattning (Slack + webb)

Kör **varje måndag kl 07:30 UTC**. Läser de senaste 7 dagarna ur arkivet (`data/archive.json`), skriver en svensk krönika med `claude-sonnet-4-6` och postar till Slack samt till fliken **Weekly** på webbsidan (senaste 52 veckorna sparas).

Om inga nya artiklar tillkommit på 7+ dagar postas istället en varning i Slack — ett tecken på att den dagliga hämtningen kan ha slutat fungera.

## Kvartalsvis trendanalys (Slack + webb)

Kör **1:a i januari, april, juli och oktober kl 08:00 UTC** — analyserar kvartalet som precis avslutats. Läser hela arkivet, jämför volym och teman över tid, och skriver en djupare analys med `claude-opus-4-8` (styrelsenivå). Postas till Slack och till fliken **Quarterly** på webbsidan.

## Veckovis uppsatsprisbevakning (Slack)

Kör **varje måndag kl 07:00 CET**. Söker igenom DiVA och SwePub efter nya kandidat- och masteruppsatser inom psykedelisk vetenskap.

**Sökperiod:** Endast uppsatser publicerade under **innevarande kalenderår** inkluderas. Priset för 2026 års uppsatser delas ut under våren 2027 — sökningen körs löpande under hela 2026 och fångar upp nya uppsatser allteftersom de publiceras. Nästa prisår (2027) börjar systemet automatiskt söka efter 2027 års uppsatser utan att något behöver ändras.

**Reaktioner i Slack:**
- 👍 Intressant kandidat · 👎 Ej relevant · 📬 Kandidat kontaktad · 📝 Ansökan inkommen

## Källor

**Global/nordiskt:**
- **PubMed** — via NCBI E-utilities API
- **Semantic Scholar** — öppet API
- **Psychedelic Alpha** — via RSS
- **DiVA** — svenska uppsatser och examensarbeten
- **SwePub** — svensk akademisk publicering (KB)

**Europeiskt (tillagt 2026):**
- **Europe PMC** — europeiska tidskrifter, kompletterar PubMed
- **EU Clinical Trials Register (EUCTR)** — aktiva och avslutade EU-kliniska prövningar
- **EMCDDA** — EU:s narkotikaövervakningsmyndighet, rapporter och nyheter
- **DART-Europe** — europeiska doktorsavhandlingar (600+ universitet)
- **OpenAIRE** — EU-finansierad öppen forskning

Artiklar dedupliceras både på DOI (fångar samma artikel från flera källor) och URL.

## Delad hämtningscache

`fetch_all()` sparar dagens resultat i `data/fetch_cache.json`. Den svenska bevakningen (06:00) hämtar live och skriver cachen; webbflödet (06:30) läser den istället för att hämta på nytt — halverar belastningen på källorna, särskilt de skörare skraparna (EUCTR, DART-Europe). Om 06:00-körningen är sen eller misslyckas hämtar webbflödet ändå live som fallback.

## Repo-struktur

```
.github/workflows/
  daily-scan.yml           # Daglig forskningsbevakning (Slack, 06:00 UTC)
  web-feed-en.yml          # Engelskt/flerspråkigt webbflöde (06:30 UTC)
  weekly-digest.yml        # Veckovis sammanfattning (måndag 07:30 UTC)
  quarterly-trends.yml     # Kvartalsvis trendanalys (1:a i kvartalsmånad)
  weekly-thesis-scan.yml   # Veckovis uppsatsprisbevakning (måndag 07:00 CET)
  backfill-archive.yml     # Manuell engångskörning: fyll arkivet med historik

src/
  main.py                  # Entry point: daglig Slack-bevakning
  web_feed.py               # Entry point: engelskt/flerspråkigt webbflöde
  weekly_digest.py          # Entry point: veckovis sammanfattning
  quarterly_trends.py       # Entry point: kvartalsvis trendanalys
  backfill_archive.py       # Engångsskript: fyll arkivet med historisk data
  thesis_main.py            # Entry point: uppsatsprisbevakning
  fetch_sources.py          # Hämtar forskningsartiklar (alla 9 källor + cache)
  fetch_theses.py           # Hämtar uppsatser (filtrerat på innevarande år)
  filter_and_summarize.py   # Relevansbedömning + FB-text (svenska)
  filter_theses.py          # Relevansbedömning för uppsatspris
  post_to_slack.py          # Slack-integration
  seen_articles.py          # Deduplikering (separata seen-filer per pipeline)

data/
  seen.json                # Sedda artiklar (daglig Slack-bevakning)
  seen_web.json             # Sedda artiklar (webbflödet)
  seen_theses.json          # Sedda uppsatser
  fetch_cache.json          # Delad hämtningscache (samma UTC-dag)
  archive.json              # Växande historik för vecko-/kvartalsanalys

docs/                       # GitHub Pages — https://ollxor.github.io/NPV/
  index.html                 # Flerspråkig sida (Feed / Weekly / Quarterly-flikar)
  data/feed.json              # Rullande flöde (senaste 60 artiklarna)
  data/weekly.json            # Veckokrönikor (senaste 52 veckorna)
  data/quarterly.json         # Kvartalsanalyser (hela historiken)

partners/                   # Onboarding-dokument för systerorganisationer
```

## AI-modeller

| Uppgift | Modell | Varför |
|---|---|---|
| Daglig filtrering + FB-text | `claude-haiku-4-5-20251001` | Hög volym, låg kostnad |
| Webbflödets filtrering + översättning | `claude-haiku-4-5-20251001` | Samma — 9 språk i ett anrop |
| Veckokrönika | `claude-sonnet-4-6` | Bättre syntes för sammanfattande text |
| Kvartalsanalys | `claude-opus-4-8` | Körs bara 4 ggr/år — kvalitet prioriteras, styrelsenivå |

Varje daglig körning kostar uppskattningsvis < 0,05 USD.

## För systerorganisationer

Se [partners/README.md](partners/README.md) för hur andra nordiska/baltiska föreningar kan sätta upp sin egen version av systemet.
