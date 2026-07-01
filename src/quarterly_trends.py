"""Quarterly trend analysis: reads the full archive and posts insights to Slack."""

import json
import os
from collections import Counter
from datetime import datetime, timezone

import anthropic
import requests

MODEL = "claude-haiku-4-5-20251001"
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ARCHIVE_FILE = os.path.join(_DATA_DIR, "archive.json")

TRENDS_PROMPT = """\
Du är analytiker för NPV (Nätverket för Psykedelisk Vetenskap) och analyserar \
trender i psykedelisk forskning och nyheter.

Nedan finns en kvartalssummering av vad bevakningen fångat upp. \
Skriv en kvartalsanalys på välformulerad svenska för NPV-styrelsen:

1. **Volymutveckling** — hur har mängden relevant forskning förändrats?
2. **Dominerande teman** — vilka ämnen växer, vilka minskar?
3. **Kliniska studier** — vad visar EUCTR-posterna om forskningsröret?
4. **Anmärkningsvärda fynd** — de viktigaste fynden detta kvartal
5. **Utblick** — kort prognos baserat på trenderna

Kvartalsvisa volymer:
{quarters}

Källfördelning detta kvartal:
{sources}

Anmärkningsvärda fynd detta kvartal:
{notable_items}

Skriv en professionell analys på max 1 200 tecken. \
Använd "psykedelika", inte "psykedeliska droger". \
Svara ENBART med analystexten."""


def _quarter_label(iso_date: str) -> str:
    try:
        d = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-K{q}"
    except Exception:
        return "okänt"


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    if not webhook and not dry_run:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")

    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Archive not found or empty.")
        return

    items = archive.get("items", [])
    if not items:
        print("Archive is empty — nothing to analyze.")
        return

    # Group by quarter
    by_quarter: dict[str, list] = {}
    for it in items:
        label = _quarter_label(it.get("added_at", ""))
        by_quarter.setdefault(label, []).append(it)

    # Quarter volume summary
    quarter_lines = []
    for label in sorted(by_quarter.keys()):
        q_items = by_quarter[label]
        notable_n = sum(1 for it in q_items if it.get("notable"))
        notable_note = f" (varav {notable_n} anmärkningsvärda)" if notable_n else ""
        quarter_lines.append(f"  {label}: {len(q_items)} artiklar{notable_note}")

    # Current quarter details
    now_label = _quarter_label(datetime.now(timezone.utc).isoformat())
    current_items = by_quarter.get(now_label, [])

    source_counts = Counter(it.get("source", "okänd") for it in current_items)
    source_lines = [f"  {src}: {n}" for src, n in source_counts.most_common()]

    notable_items = [it for it in current_items if it.get("notable")]
    notable_lines = [
        f"  - {it['title']}: {it.get('notable_reason', '')}"
        for it in notable_items[:6]
    ]
    if not notable_lines:
        notable_lines = ["  Inga anmärkningsvärda fynd registrerade detta kvartal."]

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=900,
        messages=[
            {
                "role": "user",
                "content": TRENDS_PROMPT.format(
                    quarters="\n".join(quarter_lines),
                    sources="\n".join(source_lines),
                    notable_items="\n".join(notable_lines),
                ),
            }
        ],
    )
    analysis = msg.content[0].text.strip()

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Kvartalsanalys — {now_label}",
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": analysis},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"_{len(items)} artiklar totalt i arkivet · "
                            f"{len(current_items)} detta kvartal_"
                        ),
                    }
                ],
            },
        ]
    }

    if dry_run:
        print("[DRY RUN] Quarterly analysis:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()
    print("Quarterly trend analysis posted to Slack.")


if __name__ == "__main__":
    main()
