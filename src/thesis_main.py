"""NPV Uppsatspris — veckovis genomsökning."""

import json
import os
import sys

import requests

from fetch_theses import fetch_all_theses
from filter_theses import process_theses
from seen_articles import SEEN_THESES_FILE, is_seen, mark_seen


def _webhook_url() -> str:
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")
    return url


def _post(payload: dict, dry_run: bool) -> None:
    if dry_run:
        print("[DRY RUN] Skulle posta till Slack:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    r = requests.post(_webhook_url(), json=payload, timeout=15)
    if r.status_code != 200:
        print(f"[Slack] Oväntat svar {r.status_code}: {r.text[:200]}")
    r.raise_for_status()


def post_thesis_found(item: dict, dry_run: bool = False) -> None:
    thesis = item["thesis"]
    level = item.get("level_guess", thesis.level or "uppsats").capitalize()
    reason = item.get("reason", "")

    authors_str = ""
    if thesis.authors:
        authors_str = ", ".join(thesis.authors)

    meta_parts = [p for p in [level, thesis.institution, thesis.date, authors_str] if p]
    meta_line = " · ".join(meta_parts)

    abstract_preview = thesis.abstract[:400] + "…" if len(thesis.abstract) > 400 else thesis.abstract

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🏆 Potentiell kandidat till NPV:s uppsatspris!",
                    "emoji": True,
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{thesis.title}*\n_{meta_line}_",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Sammanfattning:*\n{abstract_preview}" if abstract_preview else "_Ingen sammanfattning tillgänglig_",
                },
            },
            *(
                [
                    {
                        "type": "context",
                        "elements": [
                            {"type": "mrkdwn", "text": f"💡 _{reason}_"}
                        ],
                    }
                ]
                if reason
                else []
            ),
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{thesis.url}|🔗 Öppna uppsatsen>",
                },
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Reagera för att markera status:\n"
                            "👍 Intressant kandidat  ·  👎 Ej relevant  ·  "
                            "📬 Kandidat kontaktad  ·  📝 Ansökan inkommen"
                        ),
                    }
                ],
            },
        ]
    }
    _post(payload, dry_run=dry_run)


def post_thesis_summary(
    total: int, relevant: int, skipped: int, dry_run: bool = False
) -> None:
    if relevant > 0:
        text = (
            f"🎓 *Veckans uppsatssökning klar*\n"
            f"Hittade {total} uppsatser · {relevant} potentiella kandidater · {skipped} redan sedda\n"
            f"Källor: DiVA, SwePub"
        )
    else:
        text = (
            f"🎓 Veckans uppsatssökning klar — inga nya kandidater hittades.\n"
            f"Granskade: {total} · Redan sedda: {skipped} · Källor: DiVA, SwePub"
        )
    _post(
        {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]},
        dry_run=dry_run,
    )


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        print("=" * 60)
        print("DRY RUN — inget postas till Slack")
        print("=" * 60)

    print("\n── Hämtar uppsatser ─────────────────────────────────────")
    try:
        all_theses = fetch_all_theses()
    except Exception as e:
        print(f"Kritiskt fel vid hämtning: {e}")
        sys.exit(1)

    print(f"Totalt hämtade: {len(all_theses)}")

    new_theses = [t for t in all_theses if not is_seen(t.url, path=SEEN_THESES_FILE)]
    skipped = len(all_theses) - len(new_theses)
    print(f"Nya (ej sedda): {len(new_theses)} · Redan sedda: {skipped}")

    if not new_theses:
        print("Inga nya uppsatser — postar statusmeddelande.")
        post_thesis_summary(len(all_theses), 0, skipped, dry_run=dry_run)
        return

    print("\n── Filtrerar uppsatser ──────────────────────────────────")
    relevant_items = process_theses(new_theses)
    print(f"Relevanta kandidater: {len(relevant_items)}")

    print("\n── Postar till Slack ─────────────────────────────────────")
    for item in relevant_items:
        print(f"  Postar: {item['thesis'].title[:70]}")
        post_thesis_found(item, dry_run=dry_run)

    post_thesis_summary(len(all_theses), len(relevant_items), skipped, dry_run=dry_run)

    if not dry_run:
        mark_seen([t.url for t in all_theses], path=SEEN_THESES_FILE)
        print(f"Markerade {len(all_theses)} uppsatser som sedda.")
    else:
        print("[DRY RUN] Markerar inte uppsatser som sedda.")

    print("\nKlart.")


if __name__ == "__main__":
    main()
