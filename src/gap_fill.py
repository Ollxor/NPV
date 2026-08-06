"""One-off: recover the credit-outage window (~2026-07-30 to 2026-08-06).

Every article fetched during the outage was marked "seen" even though every
Claude filter call failed with a billing error and silently fell back to
relevant=False — nothing from that week ever got a real editorial judgment.

This re-fetches just the outage window via PubMed/Europe PMC date-range
queries (day-precise) plus a best-effort pass over the other rolling
sources (they don't support date filtering, so only items whose own date
still falls in the window survive), then runs the SAME two pipelines the
system normally uses — filter_and_summarize (Swedish, for Slack) and
web_feed (English, for the public feed + archive) — so this is a proper
catch-up, not a shortcut version.

Deliberately bypasses is_seen(): these URLs are already marked seen from
the failed run, that's exactly the bug being corrected. Does not touch
seen.json/seen_web.json itself — they're already correct and this script
never needs to consult or update them.

Set GAP_FROM / GAP_TO to override the default window. No per-destination
cap on output — a week-long gap should surface everything relevant, not
just a daily quota's worth.
"""

import os
import time
from datetime import datetime, timezone

import anthropic
from dateutil import parser as date_parser

import filter_and_summarize as slack_pipeline
import post_to_slack
import web_feed as web_pipeline
from backfill_archive import _europe_pmc_date_range, _pubmed_date_range
from fetch_sources import (
    Article,
    fetch_diva,
    fetch_openaire,
    fetch_psychedelic_alpha,
    fetch_semantic_scholar,
)

GAP_FROM = os.environ.get("GAP_FROM", "2026-07-30")
GAP_TO = os.environ.get("GAP_TO", "2026-08-06")
MAX_FILTER_BATCH = 150  # cost-safety cap on candidates sent to Claude

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_date(raw: str) -> datetime:
    if not raw:
        return _EPOCH
    try:
        d = date_parser.parse(raw, default=_EPOCH)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError, OverflowError):
        return _EPOCH


_FROM_DT = _parse_date(GAP_FROM)
_TO_DT = _parse_date(GAP_TO).replace(hour=23, minute=59, second=59)


def _in_window(article: Article) -> bool:
    d = _parse_date(article.date)
    return _FROM_DT <= d <= _TO_DT


def _added_at_for(article: Article) -> str:
    """Backdate to the article's own publish date so it lands in the right
    week/quarter for the digest and trend-analysis jobs, rather than
    showing up as "this week's news" on whatever day this script runs."""
    d = _parse_date(article.date)
    if _FROM_DT <= d <= _TO_DT:
        return d.replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
    mid = _FROM_DT + (_TO_DT - _FROM_DT) / 2
    return mid.isoformat()


def _dedup(articles: list[Article]) -> list[Article]:
    seen_dois: set[str] = set()
    seen_urls: set[str] = set()
    out: list[Article] = []
    for a in articles:
        if a.doi:
            if a.doi in seen_dois:
                continue
            seen_dois.add(a.doi)
        if a.url in seen_urls:
            continue
        seen_urls.add(a.url)
        out.append(a)
    return out


def _fetch_candidates() -> list[Article]:
    articles: list[Article] = []

    print(f"[fetch] PubMed {GAP_FROM}..{GAP_TO} (date-range)...")
    pubmed = [Article(**d) for d in _pubmed_date_range(GAP_FROM, GAP_TO)]
    print(f"  -> {len(pubmed)} articles")
    articles += pubmed

    time.sleep(2)
    print(f"[fetch] Europe PMC {GAP_FROM}..{GAP_TO} (date-range)...")
    epmc = [Article(**d) for d in _europe_pmc_date_range(GAP_FROM, GAP_TO)]
    print(f"  -> {len(epmc)} articles")
    articles += epmc

    time.sleep(2)
    print("[fetch] Rolling sources (best-effort — only items still in-window survive)...")
    # EUCTR excluded: its scraper falls back to today's date whenever it
    # can't parse a real one from the page, which would false-positive
    # match any gap-fill window ending today. Its dates are never reliable
    # enough for date-windowed recovery, only for "whatever's live right now".
    for name, fn in [
        ("Semantic Scholar", fetch_semantic_scholar),
        ("Psychedelic Alpha", fetch_psychedelic_alpha),
        ("DiVA", fetch_diva),
        ("OpenAIRE", fetch_openaire),
    ]:
        try:
            batch = fn()
        except Exception as e:
            print(f"  [{name}] error: {e}")
            continue
        print(f"  [{name}] -> {len(batch)} fetched")
        articles += batch
        time.sleep(2)

    return articles


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    if not webhook and not dry_run:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")

    print(f"Gap-fill window: {GAP_FROM} .. {GAP_TO}  |  dry_run={dry_run}\n")

    candidates = _fetch_candidates()
    candidates = [a for a in candidates if a.url and a.title]
    candidates = _dedup(candidates)
    before_window = len(candidates)
    candidates = [a for a in candidates if _in_window(a)]
    print(f"\nAfter dedup: {before_window} -> after date-window filter: {len(candidates)}")

    if len(candidates) > MAX_FILTER_BATCH:
        print(f"Capping to {MAX_FILTER_BATCH} candidates for filtering (cost safety).")
        candidates = candidates[:MAX_FILTER_BATCH]

    if not candidates:
        print("No candidates in the outage window. Nothing to do.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    # ── Slack pass (Swedish criteria — same as the daily scan) ──────────────
    print(f"\n=== Slack pass: {len(candidates)} candidates ===")
    slack_relevant: list[dict] = []
    for i, a in enumerate(candidates):
        print(f"  [{i+1}/{len(candidates)}] {a.title[:70]}")
        r = slack_pipeline.filter_article(client, a)
        if r.get("relevant"):
            slack_relevant.append({
                "article": a,
                "relevance_score": r.get("relevance_score", 3),
                "notable": r.get("notable", False),
                "notable_reason": r.get("notable_reason") or None,
                "fb_post": None,
            })
            print(f"    -> RELEVANT{' NOTABLE' if r.get('notable') else ''}")
        if i < len(candidates) - 1:
            time.sleep(0.4)
    slack_relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    print(f"Slack-relevant: {len(slack_relevant)}")

    # ── Web/archive pass (English criteria, richer fields) ──────────────────
    print(f"\n=== Web/archive pass: {len(candidates)} candidates ===")
    web_relevant: list[dict] = []
    for i, a in enumerate(candidates):
        print(f"  [{i+1}/{len(candidates)}] {a.title[:70]}")
        r = web_pipeline.filter_article(client, a)
        if r.get("relevant"):
            web_relevant.append({
                "article": a,
                "score": r.get("relevance_score", 3),
                "notable": r.get("notable", False),
                "notable_reason": r.get("notable_reason") or None,
                "study_type": r.get("study_type") or "other",
                "substances": r.get("substances") or [],
            })
            print(f"    -> RELEVANT{' NOTABLE' if r.get('notable') else ''}")
        if i < len(candidates) - 1:
            time.sleep(0.4)
    print(f"Web-relevant: {len(web_relevant)}")

    if dry_run:
        print("\n[DRY RUN] Would post to Slack:")
        for item in slack_relevant:
            print(f"  {item['article'].source} — {item['article'].title[:70]}")
        print("\n[DRY RUN] Would add to feed.json + archive.json:")
        for item in web_relevant:
            print(f"  {item['article'].source} — {item['article'].title[:70]}")
        return

    # ── Post Slack catch-up ───────────────────────────────────────────────
    if slack_relevant:
        header = {
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"📅 *Catch-up: artiklar från avbrottet {GAP_FROM} – {GAP_TO}*\n"
                        f"API-krediten tog slut och de här missades. Nu efterbehandlade "
                        f"({len(slack_relevant)} relevanta av {len(candidates)} granskade)."
                    ),
                },
            }]
        }
        post_to_slack._post(header, dry_run=dry_run)

        print(f"\n[Slack] Posting {len(slack_relevant)} catch-up articles...")
        for item in slack_relevant:
            a = item["article"]
            print(f"  Posting: {a.title[:70]}")
            item["fb_post"] = slack_pipeline.generate_fb_post(client, a)
            post_to_slack.post_article(item, dry_run=dry_run)
            time.sleep(0.5)
    else:
        print("\n[Slack] No relevant catch-up articles to post.")

    # ── Web feed + archive ───────────────────────────────────────────────
    if web_relevant:
        print(f"\n[Web] Summarizing {len(web_relevant)} articles...")
        new_items = []
        for item in web_relevant:
            a = item["article"]
            print(f"  Summarizing: {a.title[:70]}")
            summaries = web_pipeline.summarize(client, a)
            notable_reasons = None
            if item["notable"] and item["notable_reason"]:
                notable_reasons = web_pipeline.translate_reason(client, item["notable_reason"])
            new_items.append({
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "date": a.date,
                "authors": a.authors,
                "doi": a.doi,
                "summaries": summaries,
                "notable": item["notable"],
                "notable_reasons": notable_reasons,
                "relevance_score": item["score"],
                "study_type": item["study_type"],
                "substances": item["substances"],
                "added_at": _added_at_for(a),
            })
            time.sleep(0.5)

        feed = web_pipeline._load_feed()
        existing_urls = {it["url"] for it in feed["items"]}
        merged = [it for it in new_items if it["url"] not in existing_urls] + feed["items"]
        merged.sort(key=web_pipeline._publication_date, reverse=True)
        feed["items"] = merged[:web_pipeline.MAX_FEED_ITEMS]
        web_pipeline._save_feed(feed)
        print(f"Feed now holds {len(feed['items'])} items.")

        web_pipeline._append_to_archive(new_items)
    else:
        print("\n[Web] No relevant catch-up articles for the feed/archive.")

    print("\nDone.")


if __name__ == "__main__":
    main()
