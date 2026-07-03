"""Posts article summaries to Slack via Incoming Webhook."""

import os
import json
import requests


def _webhook_url() -> str:
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")
    return url


def _post(payload: dict, dry_run: bool = False) -> None:
    if dry_run:
        print("[DRY RUN] Skulle posta till Slack:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    r = requests.post(_webhook_url(), json=payload, timeout=15)
    if r.status_code != 200:
        print(f"[Slack] Oväntat svar {r.status_code}: {r.text[:200]}")
    r.raise_for_status()


def post_article(item: dict, dry_run: bool = False) -> None:
    article = item["article"]
    fb_post = item["fb_post"] or ""
    notable = item.get("notable", False)
    notable_reason = item.get("notable_reason") or ""

    authors_str = ""
    if article.authors:
        authors_str = ", ".join(article.authors[:3])
        if len(article.authors) > 3:
            authors_str += " m.fl."

    meta_parts = [p for p in [article.source, article.date, authors_str] if p]
    meta_line = " · ".join(meta_parts)

    blocks = []

    if notable:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚡ *Anmärkningsvärt fynd* — {notable_reason}" if notable_reason else "⚡ *Anmärkningsvärt fynd*",
            },
        })

    blocks += [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{article.title}*\n_{meta_line}_",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Föreslagen FB-text:*\n{fb_post}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{article.url}|🔗 Öppna originalkällan>",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "✅ publicerad · 👍 posta snart · 👎 ej relevant",
                }
            ],
        },
    ]

    _post({"blocks": blocks}, dry_run=dry_run)


def post_summary(
    total: int,
    relevant: int,
    skipped: int,
    dry_run: bool = False,
) -> None:
    sources = "PubMed · Europe PMC · Semantic Scholar · EUCTR · OpenAIRE · Psychedelic Alpha · DiVA"
    if relevant > 0:
        text = (
            f"📰 *Dagens genomsökning klar*\n"
            f"Hittade {total} artiklar · {relevant} relevanta · {skipped} redan sedda\n"
            f"_{sources}_"
        )
    else:
        text = (
            f"📰 Dagens sökning klar — inga nya relevanta artiklar hittades.\n"
            f"Totalt granskade: {total} · Redan sedda: {skipped}\n"
            f"_{sources}_"
        )

    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            }
        ]
    }
    _post(payload, dry_run=dry_run)


def post_source_health(unhealthy: list[dict], dry_run: bool = False) -> None:
    """Alert that one or more sources have stopped returning data (repeated
    hard failures). Fired once per outage by the daily scan."""
    lines = []
    for s in unhealthy:
        err = (s.get("last_error") or "")[:120]
        lines.append(f"• *{s['source']}* — {s.get('error_streak', 0)} körningar i rad: `{err}`")
    text = (
        "⚠️ *Källa(or) har slutat svara*\n"
        + "\n".join(lines)
        + "\n_Kontrollera fetch_sources.py — kan behöva uppdaterad URL/API._"
    )
    payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}
    _post(payload, dry_run=dry_run)


def post_error(message: str, dry_run: bool = False) -> None:
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *NPV Bot: Fel vid genomsökning*\n{message}",
                },
            }
        ]
    }
    _post(payload, dry_run=dry_run)
