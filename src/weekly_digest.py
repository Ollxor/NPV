"""Weekly digest: summarizes the past 7 days from the archive and posts to Slack."""

import json
import os
import re
from datetime import datetime, timedelta, timezone

import anthropic
import requests

from web_feed import LANGUAGES

MODEL = "claude-sonnet-4-6"
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_DOCS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "data")
ARCHIVE_FILE = os.path.join(_DATA_DIR, "archive.json")
WEEKLY_FILE = os.path.join(_DOCS_DATA_DIR, "weekly.json")

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

TRANSLATE_PROMPT = """\
Translate the following Swedish weekly research digest into each of these \
languages, preserving markdown **bold**, the ⚡ emoji markers, numbers, \
drug/trial names, and paragraph breaks exactly:
- en, no, da, fi, is, et, lv, lt

Swedish text:
{text}

Reply ONLY with a JSON object whose keys are the language codes above and \
whose values are the translated strings. No other text."""


def _md_to_slack(text: str) -> str:
    """Convert GitHub-style **bold** to Slack mrkdwn *bold*."""
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)


def _translate_digest(client: anthropic.Anthropic, sv_text: str) -> dict:
    """Returns {lang_code: text} for every language in LANGUAGES, including sv."""
    texts = {"sv": sv_text}
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": TRANSLATE_PROMPT.format(text=sv_text)}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        for code in LANGUAGES:
            if code != "sv":
                texts[code] = data.get(code) or sv_text
    except Exception as e:
        print(f"  [translate] Error translating digest: {e}")
        for code in LANGUAGES:
            texts.setdefault(code, sv_text)
    return texts


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

    all_items = archive.get("items", [])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    week_items = [it for it in all_items if it.get("added_at", "") >= cutoff]

    if not week_items:
        if not all_items:
            print("Archive empty — nothing to digest yet.")
            return
        # Archive has data but nothing new in 7 days → the daily feed likely
        # stopped. Turn this silent gap into a visible Slack alert.
        last_added = max((it.get("added_at", "") for it in all_items), default="")
        last_date = last_added[:10] or "okänt datum"
        warning = (
            "⚠️ *Bevakningen kan ha stannat*\n"
            "Inga nya artiklar i arkivet på 7+ dagar. "
            f"Senaste tillägg: *{last_date}*.\n"
            "Kontrollera att GitHub Actions-flödet _NPV English Web Feed_ körs "
            "utan fel."
        )
        if dry_run:
            print("[DRY RUN] Would post stale-archive warning:\n" + warning)
            return
        r = requests.post(
            webhook,
            json={"blocks": [{"type": "section",
                              "text": {"type": "mrkdwn", "text": warning}}]},
            timeout=15,
        )
        r.raise_for_status()
        print("Posted stale-archive warning to Slack.")
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
                "text": {"type": "mrkdwn", "text": _md_to_slack(digest)},
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
        print("[DRY RUN] Weekly digest (not written to disk, not posted):\n")
        print(digest)
        return

    print("Translating digest into all site languages...")
    texts = _translate_digest(client, digest)

    # Write to GitHub Pages — dedup by week so re-runs replace, not duplicate
    week_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = {
        "week_of": week_of,
        "texts": texts,
        "article_count": len(week_items),
        "notable_count": notable_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(WEEKLY_FILE, "r", encoding="utf-8") as f:
            weekly_store = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        weekly_store = {"digests": []}
    others = [d for d in weekly_store["digests"] if d.get("week_of") != week_of]
    weekly_store["digests"] = ([entry] + others)[:52]  # keep 52 weeks
    os.makedirs(os.path.dirname(WEEKLY_FILE), exist_ok=True)
    with open(WEEKLY_FILE, "w", encoding="utf-8") as f:
        json.dump(weekly_store, f, indent=2, ensure_ascii=False)
    print("Weekly digest written to docs/data/weekly.json")

    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()
    print("Weekly digest posted to Slack.")


if __name__ == "__main__":
    main()
