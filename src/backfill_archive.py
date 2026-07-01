"""One-time backfill: fetches Q2 2026 (or any date range) from date-capable
sources and all other sources, filters with Claude, and populates archive.json.

Does NOT touch seen.json or post to Slack.
Set BACKFILL_FROM / BACKFILL_TO env vars to override the default range.
"""

import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup

# Default range: Q2 of current year  (override via env)
_YEAR = datetime.utcnow().year
BACKFILL_FROM = os.environ.get("BACKFILL_FROM", f"{_YEAR}-04-01")
BACKFILL_TO   = os.environ.get("BACKFILL_TO",   f"{_YEAR}-06-30")

FILTER_MODEL = "claude-sonnet-4-6"
SUMMARY_MODEL = "claude-haiku-4-5-20251001"
MAX_FILTER_BATCH = 120   # cap total articles sent to Claude

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ARCHIVE_FILE = os.path.join(_DATA_DIR, "archive.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NPV-OmvarldsBot/1.0; "
        "+https://github.com/npv-sverige/omvarldsbevakning)"
    )
}

SUMMARY_PROMPT = """\
Write a short, clear English summary of the article below for an informed \
audience interested in psychedelic science. Maximum 400 characters. \
Neutral, scientific tone. Use "psychedelics", not "psychedelic drugs".

Title: {title}
Source: {source}
Abstract: {abstract}

Reply with ONLY the summary text."""

FILTER_PROMPT = """\
You are an editor for NPV (the Swedish Network for Psychedelic Science).

Decide whether the article below is relevant to an informed audience interested \
in psychedelic science.

Relevant = peer-reviewed research OR credible journalism about: clinical trials, \
neuroscience, psychiatry, policy and legal developments, harm reduction, or the \
anthropology of psychedelics.

NOT relevant = blog posts, speculative pieces, product promotion, designer-drug \
hype, crime reporting without scientific angle.

Notable (notable=true) = ANY of:
- Phase 2b/3 or pivotal clinical trial results published
- FDA or EMA breakthrough designation, scheduling decision, or approval
- First-in-human study for a new compound or route
- Published in Nature, Science, NEJM, Lancet, JAMA, Cell, or PNAS
- National-level policy change (legalization or scheduling)
- Large RCT (n > 200) or landmark meta-analysis

Article:
Title: {title}
Source: {source}
Abstract: {abstract}

Reply ONLY with JSON:
{{"relevant": true/false, "notable": true/false, "notable_reason": "one sentence or null"}}"""


# ── Date-filtered fetchers ──────────────────────────────────────────────────

def _pubmed_date_range(from_date: str, to_date: str) -> list[dict]:
    """Fetch PubMed articles published within a date range."""
    from_d = from_date.replace("-", "/")
    to_d   = to_date.replace("-", "/")
    search_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term=psilocybin+OR+psilocin+OR+psychedelic+OR+mdma"
        f"+OR+ayahuasca+OR+hallucinogen+OR+mescaline+OR+ketamine+AND+psychiatry"
        f"&retmax=50&sort=date&datetype=pdat&mindate={from_d}&maxdate={to_d}"
        f"&usehistory=y&retmode=json"
    )
    articles = []
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return articles
        fetch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&rettype=abstract&retmode=xml&id={','.join(ids)}"
        )
        r2 = requests.get(fetch_url, headers=HEADERS, timeout=30)
        r2.raise_for_status()
        root = ET.fromstring(r2.content)
        for el in root.findall(".//PubmedArticle"):
            try:
                pmid  = el.findtext(".//PMID", "")
                title = el.findtext(".//ArticleTitle", "").strip()
                absts = el.findall(".//AbstractText")
                abstract = " ".join((a.text or "") for a in absts).strip()
                year  = el.findtext(".//PubDate/Year", "")
                month = el.findtext(".//PubDate/Month", "")
                date  = f"{year}-{month}" if month else year
                authors_els = el.findall(".//Author")
                authors = []
                for a in authors_els[:3]:
                    last = a.findtext("LastName", "")
                    fore = a.findtext("ForeName", "")
                    if last:
                        authors.append(f"{last} {fore}".strip())
                doi = next(
                    (e.text for e in el.findall(".//ArticleId")
                     if e.get("IdType") == "doi" and e.text), ""
                )
                if title and pmid:
                    articles.append({
                        "title": title, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "source": "PubMed", "abstract": abstract,
                        "date": date, "authors": authors, "doi": doi,
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[PubMed backfill] Error: {e}")
    return articles


def _europe_pmc_date_range(from_date: str, to_date: str) -> list[dict]:
    """Fetch Europe PMC articles indexed within a date range."""
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        "?query=psilocybin+OR+psychedelic+OR+MDMA+OR+ayahuasca+OR+ketamine"
        f"&resultType=core&pageSize=25&format=json&sort=P_PDATE_D%20desc"
        f"&fromFirstIndexDate={from_date}&toFirstIndexDate={to_date}"
    )
    articles = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
        for item in results:
            doi   = item.get("doi", "")
            pmid  = item.get("pmid", "")
            pmcid = item.get("pmcid", "")
            if doi:
                link = f"https://doi.org/{doi}"
            elif pmid:
                link = f"https://europepmc.org/article/MED/{pmid}"
            elif pmcid:
                link = f"https://europepmc.org/article/PMC/{pmcid}"
            else:
                continue
            title = item.get("title", "").strip()
            if not title:
                continue
            author_str = item.get("authorString", "")
            authors = [a.strip() for a in author_str.split(",")][:3] if author_str else []
            date = item.get("firstPublicationDate", str(item.get("pubYear", "")))
            articles.append({
                "title": title, "url": link, "source": "Europe PMC",
                "abstract": item.get("abstractText", "").strip(),
                "date": date, "authors": authors, "doi": doi,
            })
    except Exception as e:
        print(f"[Europe PMC backfill] Error: {e}")
    return articles


def _fetch_rolling_sources() -> list[dict]:
    """Sources that don't support date filtering — fetch current data."""
    articles = []

    # Semantic Scholar
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search"
            "?query=psilocybin+OR+psychedelic+OR+mdma+OR+ayahuasca"
            "&fields=title,abstract,year,authors,externalIds,publicationDate"
            "&limit=20&sort=publicationDate",
            headers=HEADERS, timeout=20,
        )
        r.raise_for_status()
        for paper in r.json().get("data", []):
            ext = paper.get("externalIds") or {}
            doi = ext.get("DOI", "")
            url = (
                f"https://doi.org/{doi}" if doi
                else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}"
            )
            authors = [a.get("name","") for a in (paper.get("authors") or [])[:3]]
            articles.append({
                "title": paper.get("title","").strip(), "url": url,
                "source": "Semantic Scholar",
                "abstract": (paper.get("abstract") or "").strip(),
                "date": paper.get("publicationDate") or str(paper.get("year","")),
                "authors": authors, "doi": doi,
            })
    except Exception as e:
        print(f"[Semantic Scholar backfill] Error: {e}")

    time.sleep(2)

    # Psychedelic Alpha RSS
    try:
        feed = feedparser.parse(
            "https://psychedelicalpha.com/feed/",
            request_headers={"User-Agent": HEADERS["User-Agent"]},
        )
        for entry in feed.entries[:15]:
            articles.append({
                "title": entry.get("title","").strip(),
                "url": entry.get("link",""),
                "source": "Psychedelic Alpha",
                "abstract": BeautifulSoup(entry.get("summary",""),"lxml").get_text()[:500],
                "date": entry.get("published","")[:10],
                "authors": [], "doi": "",
            })
    except Exception as e:
        print(f"[Psychedelic Alpha backfill] Error: {e}")

    time.sleep(1)

    # EMCDDA publications RSS
    for feed_url in [
        "https://www.emcdda.europa.eu/publications/rss_en",
        "https://www.emcdda.europa.eu/news/rss_en",
    ]:
        try:
            feed = feedparser.parse(
                feed_url, request_headers={"User-Agent": HEADERS["User-Agent"]}
            )
            for entry in feed.entries[:8]:
                articles.append({
                    "title": entry.get("title","").strip(),
                    "url": entry.get("link",""),
                    "source": "EMCDDA",
                    "abstract": BeautifulSoup(entry.get("summary",""),"lxml").get_text()[:500],
                    "date": entry.get("published","")[:10],
                    "authors": [], "doi": "",
                })
        except Exception as e:
            print(f"[EMCDDA backfill] Error: {e}")

    return articles


# ── Dedup ───────────────────────────────────────────────────────────────────

def _dedup(articles: list[dict]) -> list[dict]:
    seen_dois: set[str] = set()
    seen_urls: set[str] = set()
    out = []
    for a in articles:
        if a.get("doi"):
            if a["doi"] in seen_dois:
                continue
            seen_dois.add(a["doi"])
        if a["url"] in seen_urls:
            continue
        seen_urls.add(a["url"])
        out.append(a)
    return out


# ── Filter ──────────────────────────────────────────────────────────────────

def _truncate(text: str, n: int = 1200) -> str:
    return text[:n] + "…" if len(text) > n else text


def _filter_batch(client: anthropic.Anthropic, articles: list[dict]) -> list[dict]:
    relevant = []
    for i, a in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {a['title'][:70]}")
        prompt = FILTER_PROMPT.format(
            title=a["title"], source=a["source"],
            abstract=_truncate(a.get("abstract","") or "No abstract."),
        )
        try:
            msg = client.messages.create(
                model=FILTER_MODEL, max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            if result.get("relevant"):
                a["notable"]        = result.get("notable", False)
                a["notable_reason"] = result.get("notable_reason") or None
                relevant.append(a)
                flag = " ⚡" if a["notable"] else ""
                print(f"    → RELEVANT{flag}")
            else:
                print(f"    → skip")
        except Exception as e:
            print(f"    → filter error: {e}")
        if i < len(articles) - 1:
            time.sleep(0.4)
    return relevant


# ── Summarize ──────────────────────────────────────────────────────────────

def _summarize_batch(client: anthropic.Anthropic, articles: list[dict]) -> None:
    """Add summary_en to each article in-place using Haiku."""
    print(f"\n── Generating {len(articles)} summaries with {SUMMARY_MODEL} ──────────")
    for i, a in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {a['title'][:60]}")
        prompt = SUMMARY_PROMPT.format(
            title=a["title"],
            source=a["source"],
            abstract=_truncate(a.get("abstract", "") or "No abstract."),
        )
        try:
            msg = client.messages.create(
                model=SUMMARY_MODEL, max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            a["summary_en"] = msg.content[0].text.strip()
        except Exception as e:
            print(f"    → summary error: {e}")
            a["summary_en"] = ""
        if i < len(articles) - 1:
            time.sleep(0.3)


# ── Archive write ───────────────────────────────────────────────────────────

def _added_at_for(article: dict, fallback_mid: str) -> str:
    """Use the article's publication date if it's in the backfill window, else fallback."""
    raw = article.get("date", "")
    if raw and len(raw) >= 7:
        try:
            candidate = datetime.strptime(raw[:10], "%Y-%m-%d")
            from_dt = datetime.strptime(BACKFILL_FROM, "%Y-%m-%d")
            to_dt   = datetime.strptime(BACKFILL_TO,   "%Y-%m-%d")
            if from_dt <= candidate <= to_dt:
                return candidate.strftime("%Y-%m-%dT12:00:00+00:00")
        except ValueError:
            pass
    return fallback_mid


def _write_to_archive(items: list[dict]) -> int:
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        archive = {"items": []}

    existing_urls = {it["url"] for it in archive["items"]}
    mid_quarter = f"{BACKFILL_TO}T12:00:00+00:00"

    to_add = []
    for a in items:
        if a["url"] in existing_urls:
            continue
        to_add.append({
            "title":         a["title"],
            "url":           a["url"],
            "source":        a["source"],
            "date":          a.get("date", ""),
            "authors":       a.get("authors", []),
            "doi":           a.get("doi", ""),
            "summary_en":    a.get("summary_en", ""),
            "notable":       a.get("notable", False),
            "notable_reason": a.get("notable_reason"),
            "added_at":      _added_at_for(a, mid_quarter),
        })

    archive["items"] = to_add + archive["items"]
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)
    return len(to_add)


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    print(f"Backfill range: {BACKFILL_FROM} → {BACKFILL_TO}")
    print(f"Model: {MODEL}  |  dry_run={dry_run}\n")

    print("── Fetching date-filtered sources ───────────────────────")
    print(f"[fetch] PubMed {BACKFILL_FROM}–{BACKFILL_TO}...")
    pubmed = _pubmed_date_range(BACKFILL_FROM, BACKFILL_TO)
    print(f"  → {len(pubmed)} articles")

    time.sleep(2)
    print(f"[fetch] Europe PMC {BACKFILL_FROM}–{BACKFILL_TO}...")
    epmc = _europe_pmc_date_range(BACKFILL_FROM, BACKFILL_TO)
    print(f"  → {len(epmc)} articles")

    time.sleep(2)
    print("[fetch] Rolling sources (current)...")
    rolling = _fetch_rolling_sources()
    print(f"  → {len(rolling)} articles")

    all_articles = _dedup(pubmed + epmc + rolling)
    print(f"\nTotal after dedup: {len(all_articles)}")

    # Cap to avoid excessive API cost
    if len(all_articles) > MAX_FILTER_BATCH:
        print(f"Capping to {MAX_FILTER_BATCH} articles for filtering.")
        all_articles = all_articles[:MAX_FILTER_BATCH]

    print(f"\n── Filtering with {MODEL} ────────────────────────────────")
    client = anthropic.Anthropic(api_key=api_key)
    relevant = _filter_batch(client, all_articles)
    notable_n = sum(1 for a in relevant if a.get("notable"))
    print(f"\nRelevant: {len(relevant)}  |  Notable: {notable_n}")

    if dry_run:
        print("\n[DRY RUN] Would write to archive:")
        for a in relevant:
            flag = " ⚡" if a.get("notable") else ""
            print(f"  {a['source']}{flag} — {a['title'][:70]}")
        return

    _summarize_batch(client, relevant)
    added = _write_to_archive(relevant)
    print(f"\nWrote {added} new items to archive.json.")
    print("Done. Run the quarterly trend analysis next.")


if __name__ == "__main__":
    main()
