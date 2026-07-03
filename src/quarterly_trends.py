"""Quarterly trend analysis: reads the full archive and posts insights to Slack."""

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import anthropic
import requests

from web_feed import LANGUAGES

MODEL = "claude-opus-4-8"
TRANSLATE_MODEL = "claude-sonnet-4-6"  # translation doesn't need Opus
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_DOCS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "data")
ARCHIVE_FILE = os.path.join(_DATA_DIR, "archive.json")
QUARTERLY_FILE = os.path.join(_DOCS_DATA_DIR, "quarterly.json")

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


def _md_to_slack(text: str) -> str:
    """Convert GitHub-style **bold** to Slack mrkdwn *bold*."""
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)


TRANSLATE_PROMPT = """\
Translate the following Swedish quarterly research trend analysis into each \
of these languages, preserving markdown **bold**, numbered sections, numbers, \
drug/trial names, and paragraph breaks exactly:
- en, no, da, fi, is, et, lv, lt

Swedish text:
{text}

Reply ONLY with a JSON object whose keys are the language codes above and \
whose values are the translated strings. No other text."""


def _translate_analysis(client: anthropic.Anthropic, sv_text: str) -> dict:
    """Returns {lang_code: text} for every language in LANGUAGES, including sv."""
    texts = {"sv": sv_text}
    try:
        msg = client.messages.create(
            model=TRANSLATE_MODEL,
            max_tokens=3500,
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
        print(f"  [translate] Error translating analysis: {e}")
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

    # Analyze the quarter that JUST ENDED, not the one that just started.
    # This job is scheduled for the 1st of Jan/Apr/Jul/Oct — "today" is
    # already the new quarter, so "yesterday" reliably lands in the
    # completed quarter whether this runs on schedule or is triggered
    # manually right at a quarter boundary (as happened 2026-07-01).
    target_dt = datetime.now(timezone.utc) - timedelta(days=1)
    now_label = _quarter_label(target_dt.isoformat())
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
                "text": {"type": "mrkdwn", "text": _md_to_slack(analysis)},
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
        print("[DRY RUN] Quarterly analysis (not written to disk, not posted):\n")
        print(analysis)
        return

    print("Translating analysis into all site languages...")
    texts = _translate_analysis(client, analysis)

    # Write to GitHub Pages — dedup by quarter so re-runs replace, not duplicate
    entry = {
        "quarter": now_label,
        "texts": texts,
        "total_archive": len(items),
        "quarter_count": len(current_items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(QUARTERLY_FILE, "r", encoding="utf-8") as f:
            quarterly_store = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        quarterly_store = {"analyses": []}
    others = [a for a in quarterly_store["analyses"] if a.get("quarter") != now_label]
    quarterly_store["analyses"] = [entry] + others
    os.makedirs(os.path.dirname(QUARTERLY_FILE), exist_ok=True)
    with open(QUARTERLY_FILE, "w", encoding="utf-8") as f:
        json.dump(quarterly_store, f, indent=2, ensure_ascii=False)
    print("Quarterly analysis written to docs/data/quarterly.json")

    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()
    print("Quarterly trend analysis posted to Slack.")


if __name__ == "__main__":
    main()
