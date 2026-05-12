"""Relevance filtering and FB-post generation via Claude."""

import json
import os
import time

import anthropic

from fetch_sources import Article

MODEL = "claude-haiku-4-5-20251001"
MAX_ARTICLES_PER_RUN = 5

FILTER_PROMPT = """\
Du är redaktör för NPV (Nätverket för Psykedelisk Vetenskap), en svensk ideell förening som sprider kunskap om psykedelisk forskning.

Bedöm om följande artikel är relevant att dela med en välutbildad, psykedeliskt intresserad publik på Facebook.

Relevant = peer-reviewed forskning ELLER trovärdig nyhetsartikel om: kliniska studier, neurovetenskap, psykiatri, politisk/legal utveckling, harm reduction, antropologi kring psykedelika.

INTE relevant = blogginlägg, spekulativa artiklar, produktreklam, kryptodroger, kriminalrapportering utan vetenskaplig vinkling.

Artikel:
Titel: {title}
Källa: {source}
Sammanfattning/abstract: {abstract}

Svara ENBART med JSON: {{"relevant": true/false, "reason": "kort motivering på svenska", "relevance_score": 1-5}}"""

FB_POST_PROMPT = """\
Du är social media-redaktör för NPV (Nätverket för Psykedelisk Vetenskap).

Skriv ett Facebook-inlägg på välformulerad, lättbegriplig svenska för en kunnig publik.

REGLER:
- Max 500 tecken
- Inga talstreck eller bindestreck
- Använd INTE "psykedeliska droger" — använd "psykedelika"
- Om tillämpligt: nämn studiedesign och centrala data
- Avsluta inte med "Länk i bio" eller liknande
- Neutral, vetenskaplig ton — inte hype

Artikel:
Titel: {title}
Källa/journal: {source}
Abstract/sammanfattning: {abstract}
URL: {url}

Skriv ENBART FB-texten, ingen förklaring."""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def _truncate(text: str, max_chars: int = 1500) -> str:
    return text[:max_chars] + "…" if len(text) > max_chars else text


def filter_article(client: anthropic.Anthropic, article: Article) -> dict:
    """Returns {"relevant": bool, "reason": str, "relevance_score": int}."""
    prompt = FILTER_PROMPT.format(
        title=article.title,
        source=article.source,
        abstract=_truncate(article.abstract or "Ingen sammanfattning tillgänglig."),
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"  [filter] Error for '{article.title[:60]}': {e}")
        return {"relevant": False, "reason": "Fel vid bedömning", "relevance_score": 1}


def generate_fb_post(client: anthropic.Anthropic, article: Article) -> str:
    """Returns suggested Facebook post text."""
    prompt = FB_POST_PROMPT.format(
        title=article.title,
        source=article.source,
        abstract=_truncate(article.abstract or "Ingen sammanfattning tillgänglig."),
        url=article.url,
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  [fb_post] Error for '{article.title[:60]}': {e}")
        return f"Ny artikel: {article.title}\n{article.url}"


def process_articles(articles: list[Article]) -> list[dict]:
    """
    Filters articles for relevance, generates FB posts for relevant ones.
    Returns list of dicts with keys: article, fb_post, relevance_score, reason.
    Caps output at MAX_ARTICLES_PER_RUN by relevance_score.
    """
    client = _client()
    relevant: list[dict] = []

    print(f"[filter] Bedömer {len(articles)} artiklar...")
    for i, article in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {article.title[:70]}")
        result = filter_article(client, article)
        print(f"    → relevant={result.get('relevant')}, score={result.get('relevance_score')}, {result.get('reason', '')[:80]}")
        if result.get("relevant"):
            relevant.append(
                {
                    "article": article,
                    "relevance_score": result.get("relevance_score", 3),
                    "reason": result.get("reason", ""),
                    "fb_post": None,
                }
            )
        # Be polite to the API
        if i < len(articles) - 1:
            time.sleep(0.5)

    # Sort by score descending, take top N
    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    relevant = relevant[:MAX_ARTICLES_PER_RUN]

    print(f"[fb_post] Genererar FB-text för {len(relevant)} relevanta artiklar...")
    for item in relevant:
        article = item["article"]
        print(f"  Genererar för: {article.title[:70]}")
        item["fb_post"] = generate_fb_post(client, article)
        time.sleep(0.5)

    return relevant
