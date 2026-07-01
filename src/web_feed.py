"""English-language public web feed.

Reuses the existing fetcher, filters and summarizes in English with Claude,
and writes a rolling JSON feed that the static page in docs/ renders.
Published via GitHub Pages — no Slack, no server required.
"""

import json
import os
import time
from datetime import datetime, timezone

import anthropic

from fetch_sources import Article, fetch_all
from seen_articles import is_seen, mark_seen

MODEL = "claude-haiku-4-5-20251001"
MAX_PER_RUN = 8          # max new summaries generated per run
MAX_FEED_ITEMS = 60      # rolling cap of items kept on the page

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_DOCS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "data")
SEEN_WEB_FILE = os.path.join(_DATA_DIR, "seen_web.json")
FEED_FILE = os.path.join(_DOCS_DATA_DIR, "feed.json")
ARCHIVE_FILE = os.path.join(_DATA_DIR, "archive.json")

# Summary languages: English (default) + Nordic and Baltic languages.
LANGUAGES = {
    "en": "English",
    "sv": "Swedish",
    "no": "Norwegian (Bokmål)",
    "da": "Danish",
    "fi": "Finnish",
    "is": "Icelandic",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
}

FILTER_PROMPT = """\
You are the editor of an English-language news feed about psychedelic science, \
run by NPV (the Swedish Network for Psychedelic Science).

Decide whether the following article is relevant to share with an informed, \
internationally minded audience interested in psychedelic research.

Relevant = peer-reviewed research OR credible journalism about: clinical trials, \
neuroscience, psychiatry, policy and legal developments, harm reduction, or the \
anthropology of psychedelics.

NOT relevant = blog posts, speculative pieces, product promotion, designer-drug \
hype, or crime reporting without a scientific angle.

Notable (notable=true) = ANY of the following:
- Phase 2b/3 or pivotal clinical trial results published
- FDA or EMA breakthrough designation, scheduling decision, or approval
- First-in-human study for a new compound or route of administration
- Published in Nature, Science, NEJM, Lancet, JAMA, Cell, or PNAS
- National-level policy change (legalization or scheduling change)
- Large RCT (n > 200) or landmark meta-analysis across multiple compounds

Article:
Title: {title}
Source: {source}
Abstract/summary: {abstract}

Reply ONLY with JSON:
{{"relevant": true/false, "reason": "short reason in English", "relevance_score": 1-5, "notable": true/false, "notable_reason": "one sentence why (e.g. Phase 3 RCT in NEJM, n=233), or null"}}"""

SUMMARY_PROMPT = """\
You are the editor of a multilingual feed about psychedelic science run by NPV \
(the Swedish Network for Psychedelic Science).

Write a short, clear summary of the article below for a knowledgeable audience, \
and provide that summary in EACH of these languages:
- en: English
- sv: Swedish
- no: Norwegian (Bokmål)
- da: Danish
- fi: Finnish
- is: Icelandic
- et: Estonian
- lv: Latvian
- lt: Lithuanian

RULES (apply to every language):
- Maximum 500 characters
- Neutral, scientific tone — no hype
- Use the local equivalent of "psychedelics", not "psychedelic drugs"
- Mention study design and key data where applicable
- Write naturally and fluently for a native reader of that language

Article:
Title: {title}
Source/journal: {source}
Abstract/summary: {abstract}
URL: {url}

Reply ONLY with a JSON object whose keys are the language codes \
(en, sv, no, da, fi, is, et, lv, lt) and whose values are the summary strings. \
No other text."""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def _truncate(text: str, max_chars: int = 1500) -> str:
    return text[:max_chars] + "…" if len(text) > max_chars else text


def filter_article(client: anthropic.Anthropic, article: Article) -> dict:
    prompt = FILTER_PROMPT.format(
        title=article.title,
        source=article.source,
        abstract=_truncate(article.abstract or "No abstract available."),
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"  [filter] Error for '{article.title[:60]}': {e}")
        return {"relevant": False, "reason": "Assessment error", "relevance_score": 1, "notable": False, "notable_reason": None}


def summarize(client: anthropic.Anthropic, article: Article) -> dict:
    """Returns {lang_code: summary} for every language in LANGUAGES."""
    prompt = SUMMARY_PROMPT.format(
        title=article.title,
        source=article.source,
        abstract=_truncate(article.abstract or "No abstract available."),
        url=article.url,
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        fallback = data.get("en") or article.title
        return {code: (data.get(code) or fallback) for code in LANGUAGES}
    except Exception as e:
        print(f"  [summary] Error for '{article.title[:60]}': {e}")
        return {code: article.title for code in LANGUAGES}


def _load_feed() -> dict:
    try:
        with open(FEED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"generated_at": "", "items": []}


def _save_feed(feed: dict) -> None:
    os.makedirs(os.path.dirname(FEED_FILE), exist_ok=True)
    feed["generated_at"] = datetime.now(timezone.utc).isoformat()
    with open(FEED_FILE, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2, ensure_ascii=False)


def _append_to_archive(new_items: list[dict]) -> None:
    """Append new feed items to the growing archive (English summary only)."""
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        archive = {"items": []}
    existing_urls = {it["url"] for it in archive["items"]}
    to_add = [
        {
            "title": it["title"],
            "url": it["url"],
            "source": it["source"],
            "date": it["date"],
            "authors": it.get("authors", []),
            "doi": it.get("doi", ""),
            "summary_en": (it.get("summaries") or {}).get("en", ""),
            "notable": it.get("notable", False),
            "notable_reason": it.get("notable_reason"),
            "added_at": it["added_at"],
        }
        for it in new_items
        if it["url"] not in existing_urls
    ]
    archive["items"] = to_add + archive["items"]  # newest first
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)
    print(f"Archive: added {len(to_add)} items · total {len(archive['items'])}.")


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        print("=" * 60)
        print("DRY RUN — feed.json will not be written")
        print("=" * 60)

    print("\n── Fetching articles ────────────────────────────────────")
    all_articles = fetch_all()
    print(f"Total fetched: {len(all_articles)}")

    new_articles = [a for a in all_articles if not is_seen(a.url, path=SEEN_WEB_FILE)]
    skipped = len(all_articles) - len(new_articles)
    print(f"New (unseen): {len(new_articles)} · Already seen: {skipped}")

    if not new_articles:
        print("No new articles — nothing to add.")
        return

    client = _client()
    relevant: list[dict] = []

    print("\n── Filtering ────────────────────────────────────────────")
    for i, article in enumerate(new_articles):
        print(f"  [{i+1}/{len(new_articles)}] {article.title[:70]}")
        result = filter_article(client, article)
        print(f"    → relevant={result.get('relevant')}, score={result.get('relevance_score')}")
        if result.get("relevant"):
            relevant.append({
                "article": article,
                "score": result.get("relevance_score", 3),
                "notable": result.get("notable", False),
                "notable_reason": result.get("notable_reason") or None,
            })
        if i < len(new_articles) - 1:
            time.sleep(0.5)

    relevant.sort(key=lambda x: x["score"], reverse=True)
    relevant = relevant[:MAX_PER_RUN]
    print(f"Relevant this run: {len(relevant)}")

    print("\n── Summarizing ──────────────────────────────────────────")
    now = datetime.now(timezone.utc).isoformat()
    new_items = []
    for item in relevant:
        article = item["article"]
        print(f"  Summarizing: {article.title[:70]}")
        new_items.append(
            {
                "title": article.title,
                "url": article.url,
                "source": article.source,
                "date": article.date,
                "authors": article.authors,
                "doi": article.doi,
                "summaries": summarize(client, article),
                "notable": item["notable"],
                "notable_reason": item["notable_reason"],
                "added_at": now,
            }
        )
        time.sleep(0.5)

    if dry_run:
        print("\n[DRY RUN] Would add these items:")
        print(json.dumps(new_items, ensure_ascii=False, indent=2))
        return

    # Merge into rolling feed (newest first, dedup by URL, capped)
    feed = _load_feed()
    existing_urls = {it["url"] for it in feed["items"]}
    merged = [it for it in new_items if it["url"] not in existing_urls] + feed["items"]
    feed["items"] = merged[:MAX_FEED_ITEMS]
    _save_feed(feed)
    print(f"\nFeed now holds {len(feed['items'])} items.")

    _append_to_archive(new_items)
    mark_seen([a.url for a in all_articles], path=SEEN_WEB_FILE)
    print(f"Marked {len(all_articles)} articles as seen.")
    print("\nDone.")


if __name__ == "__main__":
    main()
