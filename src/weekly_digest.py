"""Weekly digest: summarizes the past 7 days from the archive and posts to Slack."""

import json
import os
import time
from datetime import datetime, timedelta, timezone

import anthropic
import requests

MODEL = "claude-sonnet-4-6"
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ARCHIVE_FILE = os.path.join(_DATA_DIR, "archive.json")

DIGEST_PROMPT = """\
Du är redaktör för NPV (Nätverket för Psykedelisk Vetenskap).

Nedan finns de artiklar som samlats in under den senaste veckan via \
den automatiska bevakningen. Skriv en kortfattad veckokrönika på \
välformulerad svenska för NPV-teamet:

- 3–5 punkter som lyfter fram veckans viktigaste teman eller fynd
- Markera eventuella anmärkningsvärda fynd (märkta med ⚡)
- Avsluta med en kort mening om eventuella trender eller utblick
- Max 900 tecken totalt
- Använd "psykedelika", inte "psykedeliska droger"
- Neutral, vetenskaplig ton

Veckans artiklar:
{articles}

Svara ENBART med kröniketexten, inga rubriker eller JSON."""


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
        print("Archive not found or empty — nothing to digest.")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    week_items = [
        it for it in archive.get("items", [])
        if it.get("added_at", "") >= cutoff
    ]

    if not week_items:
        print("No items in the past 7 days — skipping digest.")
        return

    print(f"Found {len(week_items)} items from the past week.")

    lines = []
    for it in week_items:
        flag = " ⚡" if it.get("notable") else ""
        reason = f" ({it['notable_reason']})" if it.get("notable_reason") else ""
        summary = it.get("summary_en", "")[:200]
        lines.append(f"- [{it['source']}]{flag}{reason} {it['title']}: {summary}")
    articles_text = "\n".join(lines)

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=700,
        messages=[{"role": "user", "content": DIGEST_PROMPT.format(articles=articles_text)}],
    )
    digest = msg.content[0].text.strip()

    notable_count = sum(1 for it in week_items if it.get("notable"))
    notable_note = f" · {notable_count} anmärkningsvärda" if notable_count else ""

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📅 Veckans psykedeliska forskning"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": digest},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_{len(week_items)} artiklar granskade denna vecka{notable_note}_",
                    }
                ],
            },
        ]
    }

    if dry_run:
        print("[DRY RUN] Weekly digest:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()
    print("Weekly digest posted to Slack.")


if __name__ == "__main__":
    main()
