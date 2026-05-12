# NPV Omvärldsbevakning

Automatisk daglig sökning efter psykedelisk forskning och nyheter, med AI-genererade Facebook-inlägg som postas till Slack för redaktionell granskning.

## Hur det fungerar

1. Kör varje dag kl 07:00 CET via GitHub Actions
2. Hämtar nya artiklar från PubMed, Semantic Scholar, Psychedelic Alpha och DiVA
3. Filtrerar bort irrelevant innehåll med Claude (Haiku)
4. Genererar ett förslag på Facebook-text per relevant artikel
5. Postar till Slack — styrelsen röstar med emoji-reaktioner

**Reaktioner i Slack:**
- ✅ publicerad
- 👍 bra, posta snart
- 👎 ej relevant

## Kom igång

### 1. Klona repot och skapa GitHub Secrets

Gå till **Settings → Secrets and variables → Actions** i repot och lägg till:

| Secret | Beskrivning |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Hämtas från [console.anthropic.com](https://console.anthropic.com) |
| `SLACK_WEBHOOK_URL` | Se instruktioner nedan |

### 2. Skapa Slack-webhook

1. Gå till [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch**
2. Namn: `NPV Omvärldsbevakning` · Workspace: NPVs Slack
3. Under **Incoming Webhooks**: aktivera → **Add New Webhook to Workspace**
4. Välj kanalen `#omvarldsbevakning` (skapa den först i Slack om den inte finns)
5. Kopiera webhook-URL:en → lägg in som `SLACK_WEBHOOK_URL` i GitHub Secrets

### 3. Kör manuellt för test

Gå till **Actions → NPV Daglig omvärldsbevakning → Run workflow** och välj `dry_run: true` för att testa utan att posta till Slack.

Lokalt:
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
DRY_RUN=true python src/main.py
```

## Repo-struktur

```
.github/workflows/daily-scan.yml   # GitHub Actions cron-jobb
src/
  main.py                          # Entry point
  fetch_sources.py                 # Hämtar från RSS/API-källor
  filter_and_summarize.py          # Claude API-anrop (filter + FB-text)
  post_to_slack.py                 # Slack Incoming Webhook
  seen_articles.py                 # Deduplikering via seen.json
data/
  seen.json                        # Persisterat register över postade artiklar
requirements.txt
```

## Källor

- **PubMed** — via NCBI E-utilities API
- **Semantic Scholar** — öppet API, ingen nyckel krävs
- **Psychedelic Alpha** — via RSS (scraping som fallback)
- **DiVA** — svenska examensarbeten via Atom-feed

## AI-modell

Använder `claude-haiku-4-5-20251001` för att hålla kostnaderna låga. Varje daglig körning kostar uppskattningsvis < 0,05 USD.

## Framtida utbyggnad (ej implementerat)

- Enkel webbvy (GitHub Pages) med lista på alla förslag och deras Slack-status
- Bild-pipeline: Playwright tar skärmdump, lägger NPV-grafisk mall ovanpå
- Automatisk export av godkända inlägg (👍-reaktion) till Google Sheet
