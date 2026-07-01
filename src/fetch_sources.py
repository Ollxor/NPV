"""Fetches articles from all configured sources."""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NPV-OmvarldsBot/1.0; "
        "+https://github.com/npv-sverige/omvarldsbevakning)"
    )
}

PUBMED_SEARCH = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=pubmed&term=psilocybin+OR+psilocin+OR+psychedelic+OR+mdma"
    "+OR+ayahuasca+OR+hallucinogen+OR+mescaline+OR+ketamine+AND+psychiatry"
    "&retmax=20&sort=date&usehistory=y&retmode=json"
)
PUBMED_FETCH = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pubmed&rettype=abstract&retmode=xml"
)
SEMANTIC_SCHOLAR_API = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
    "?query=psilocybin+OR+psychedelic+OR+mdma+OR+ayahuasca"
    "&fields=title,abstract,year,authors,externalIds,publicationDate"
    "&limit=10&sort=publicationDate"
)
PSYCHEDELIC_ALPHA_RSS = "https://psychedelicalpha.com/feed/"
PSYCHEDELIC_ALPHA_NEWS = "https://psychedelicalpha.com/news/"
DIVA_ATOM = (
    "https://www.diva-portal.org/smash/export.jsf"
    "?format=atom&query=psilocybin+OR+psykedelika"
    "&aq=%5B%5B%5D%5D&aq2=%5B%5B%5D%5D&aqe=%5B%5D"
    "&noOfRows=10&sortOrder=dateSort_sort_desc&onlyFullText=false&sf=all"
)

# European sources
EUROPE_PMC_API = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    "?query=psilocybin+OR+psychedelic+OR+MDMA+OR+ayahuasca+OR+ketamine"
    "&resultType=core&pageSize=10&format=json&sort=P_PDATE_D%20desc"
)
EUCTR_SEARCH = (
    "https://www.clinicaltrialsregister.eu/ctr-search/search"
    "?query=psilocybin+OR+psychedelic+OR+MDMA+OR+ketamine"
)
EMCDDA_PUB_RSS = "https://www.emcdda.europa.eu/publications/rss_en"
EMCDDA_NEWS_RSS = "https://www.emcdda.europa.eu/news/rss_en"
DART_EUROPE_SEARCH = (
    "https://www.dart-europe.eu/simple-search"
    "?query=psilocybin+OR+psychedelic+OR+MDMA+OR+ayahuasca"
)
OPENAIRE_API = (
    "https://api.openaire.eu/search/publications"
    "?keywords=psilocybin+psychedelic&format=json&size=10"
    "&sortBy=dateofacceptance,descending"
)


@dataclass
class Article:
    title: str
    url: str
    source: str
    abstract: str = ""
    date: str = ""
    authors: list[str] = field(default_factory=list)
    doi: str = ""


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# ── PubMed ─────────────────────────────────────────────────────────────────


def fetch_pubmed() -> list[Article]:
    articles: list[Article] = []
    try:
        r = requests.get(PUBMED_SEARCH, headers=HEADERS, timeout=20)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return articles

        fetch_url = PUBMED_FETCH + "&id=" + ",".join(ids)
        r2 = requests.get(fetch_url, headers=HEADERS, timeout=30)
        r2.raise_for_status()
        root = ET.fromstring(r2.content)

        for article_el in root.findall(".//PubmedArticle"):
            try:
                pmid = article_el.findtext(".//PMID", "")
                title = article_el.findtext(".//ArticleTitle", "").strip()
                abstract_texts = article_el.findall(".//AbstractText")
                abstract = " ".join(
                    (el.text or "") for el in abstract_texts
                ).strip()
                year = article_el.findtext(".//PubDate/Year", "")
                month = article_el.findtext(".//PubDate/Month", "")
                date = f"{year}-{month}" if month else year
                authors_els = article_el.findall(".//Author")
                authors = []
                for a in authors_els[:3]:
                    last = a.findtext("LastName", "")
                    fore = a.findtext("ForeName", "")
                    if last:
                        authors.append(f"{last} {fore}".strip())

                doi = next(
                    (el.text for el in article_el.findall(".//ArticleId")
                     if el.get("IdType") == "doi" and el.text),
                    ""
                )
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                if title and pmid:
                    articles.append(
                        Article(
                            title=title,
                            url=url,
                            source="PubMed",
                            abstract=abstract,
                            date=date,
                            authors=authors,
                            doi=doi,
                        )
                    )
            except Exception:
                continue
    except Exception as e:
        print(f"[PubMed] Error: {e}")
    return articles


# ── Semantic Scholar ────────────────────────────────────────────────────────


def fetch_semantic_scholar() -> list[Article]:
    articles: list[Article] = []
    try:
        r = requests.get(SEMANTIC_SCHOLAR_API, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [])
        for paper in data:
            ext = paper.get("externalIds") or {}
            doi = ext.get("DOI", "")
            url = (
                f"https://doi.org/{doi}"
                if doi
                else f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"
            )
            authors = [
                a.get("name", "") for a in (paper.get("authors") or [])[:3]
            ]
            articles.append(
                Article(
                    title=paper.get("title", "").strip(),
                    url=url,
                    source="Semantic Scholar",
                    abstract=(paper.get("abstract") or "").strip(),
                    date=paper.get("publicationDate") or str(paper.get("year", "")),
                    authors=authors,
                    doi=doi,
                )
            )
    except Exception as e:
        print(f"[Semantic Scholar] Error: {e}")
    return articles


# ── Psychedelic Alpha ───────────────────────────────────────────────────────


def fetch_psychedelic_alpha() -> list[Article]:
    articles: list[Article] = []

    # Try RSS first
    try:
        feed = feedparser.parse(
            PSYCHEDELIC_ALPHA_RSS, request_headers={"User-Agent": HEADERS["User-Agent"]}
        )
        if feed.entries:
            for entry in feed.entries[:10]:
                articles.append(
                    Article(
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", ""),
                        source="Psychedelic Alpha",
                        abstract=BeautifulSoup(
                            entry.get("summary", ""), "lxml"
                        ).get_text()[:500],
                        date=entry.get("published", _today_str())[:10],
                    )
                )
            return articles
    except Exception:
        pass

    # Fallback: scrape news index
    try:
        time.sleep(2)
        r = requests.get(PSYCHEDELIC_ALPHA_NEWS, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for item in soup.select("article, .post, .news-item")[:10]:
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if not href.startswith("http"):
                href = "https://psychedelicalpha.com" + href
            articles.append(
                Article(
                    title=title,
                    url=href,
                    source="Psychedelic Alpha",
                    abstract="",
                    date=_today_str(),
                )
            )
    except Exception as e:
        print(f"[Psychedelic Alpha] Error: {e}")
    return articles


# ── DiVA ───────────────────────────────────────────────────────────────────


def fetch_diva() -> list[Article]:
    articles: list[Article] = []
    try:
        r = requests.get(DIVA_ATOM, headers=HEADERS, timeout=20)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        for entry in feed.entries[:10]:
            articles.append(
                Article(
                    title=entry.get("title", "").strip(),
                    url=entry.get("link", entry.get("id", "")),
                    source="DiVA",
                    abstract=BeautifulSoup(
                        entry.get("summary", ""), "lxml"
                    ).get_text()[:500],
                    date=entry.get("published", _today_str())[:10],
                )
            )
    except Exception as e:
        print(f"[DiVA] Error: {e}")
    return articles


# ── Europe PMC ─────────────────────────────────────────────────────────────


def fetch_europe_pmc() -> list[Article]:
    articles: list[Article] = []
    try:
        r = requests.get(EUROPE_PMC_API, headers=HEADERS, timeout=20)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
        for item in results:
            doi = item.get("doi", "")
            pmid = item.get("pmid", "")
            pmcid = item.get("pmcid", "")
            if doi:
                url = f"https://doi.org/{doi}"
            elif pmid:
                url = f"https://europepmc.org/article/MED/{pmid}"
            elif pmcid:
                url = f"https://europepmc.org/article/PMC/{pmcid}"
            else:
                continue
            title = item.get("title", "").strip()
            if not title:
                continue
            author_str = item.get("authorString", "")
            authors = [a.strip() for a in author_str.split(",")][:3] if author_str else []
            date = item.get("firstPublicationDate", str(item.get("pubYear", "")))
            articles.append(
                Article(
                    title=title,
                    url=url,
                    source="Europe PMC",
                    abstract=item.get("abstractText", "").strip(),
                    date=date,
                    authors=authors,
                    doi=doi,
                )
            )
    except Exception as e:
        print(f"[Europe PMC] Error: {e}")
    return articles


# ── EU Clinical Trials Register ─────────────────────────────────────────────


def fetch_euctr() -> list[Article]:
    articles: list[Article] = []
    try:
        time.sleep(2)
        r = requests.get(EUCTR_SEARCH, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for trial in soup.select(".result, li.result, .search-result")[:10]:
            a_tag = trial.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if not href.startswith("http"):
                href = "https://www.clinicaltrialsregister.eu" + href
            desc_el = trial.find(class_=["outcome", "objective", "description", "summary"])
            abstract = desc_el.get_text(strip=True)[:500] if desc_el else ""
            date_el = trial.find(class_=["date", "start-date", "first-received"])
            date = date_el.get_text(strip=True)[:10] if date_el else _today_str()
            if title:
                articles.append(
                    Article(
                        title=title,
                        url=href,
                        source="EU Clinical Trials Register",
                        abstract=abstract,
                        date=date,
                    )
                )
    except Exception as e:
        print(f"[EUCTR] Error: {e}")
    return articles


# ── EMCDDA ─────────────────────────────────────────────────────────────────


def fetch_emcdda() -> list[Article]:
    articles: list[Article] = []
    for feed_url in [EMCDDA_PUB_RSS, EMCDDA_NEWS_RSS]:
        try:
            feed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": HEADERS["User-Agent"]}
            )
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                url = entry.get("link", "")
                if not (title and url):
                    continue
                articles.append(
                    Article(
                        title=title,
                        url=url,
                        source="EMCDDA",
                        abstract=BeautifulSoup(
                            entry.get("summary", ""), "lxml"
                        ).get_text()[:500],
                        date=entry.get("published", _today_str())[:10],
                    )
                )
        except Exception as e:
            print(f"[EMCDDA] Error for {feed_url}: {e}")
    return articles


# ── DART-Europe ─────────────────────────────────────────────────────────────


def fetch_dart_europe() -> list[Article]:
    articles: list[Article] = []
    try:
        time.sleep(2)
        r = requests.get(DART_EUROPE_SEARCH, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        # DART-Europe renders results as table rows or artifact-title divs
        for row in soup.select("tr.odd, tr.even, .artifact-title, .ds-artifact-item")[:10]:
            a_tag = row.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if not href.startswith("http"):
                href = "https://www.dart-europe.eu" + href
            cells = row.find_all("td")
            date = _today_str()
            if len(cells) >= 2:
                candidate = cells[-1].get_text(strip=True)
                if candidate and len(candidate) >= 4 and candidate[:4].isdigit():
                    date = candidate[:10]
            if title:
                articles.append(
                    Article(
                        title=title,
                        url=href,
                        source="DART-Europe",
                        abstract="",
                        date=date,
                    )
                )
    except Exception as e:
        print(f"[DART-Europe] Error: {e}")
    return articles


# ── OpenAIRE ───────────────────────────────────────────────────────────────


def _openaire_str(obj) -> str:
    """Extract a string value from OpenAIRE's deeply nested JSON."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("$", "")
    if isinstance(obj, list) and obj:
        return _openaire_str(obj[0])
    return ""


def fetch_openaire() -> list[Article]:
    articles: list[Article] = []
    try:
        r = requests.get(OPENAIRE_API, headers=HEADERS, timeout=30)
        r.raise_for_status()
        results = (
            r.json()
            .get("response", {})
            .get("results", {})
            .get("result", [])
        )
        if not isinstance(results, list):
            results = [results]
        for item in results:
            meta = (
                item.get("metadata", {})
                .get("oaf:entity", {})
                .get("oaf:result", {})
            )
            title = _openaire_str(meta.get("title", ""))
            if not title:
                continue

            # DOI → best URL
            pids = meta.get("pid", [])
            if not isinstance(pids, list):
                pids = [pids]
            doi = next(
                (
                    p.get("$", "")
                    for p in pids
                    if isinstance(p, dict) and p.get("@classid") == "doi"
                ),
                "",
            )
            url = f"https://doi.org/{doi}" if doi else ""

            # Fallback: first web resource in instances
            if not url:
                instances = meta.get("instance", [])
                if not isinstance(instances, list):
                    instances = [instances]
                for inst in instances:
                    wr = inst.get("webresource", []) if isinstance(inst, dict) else []
                    if not isinstance(wr, list):
                        wr = [wr]
                    for w in wr:
                        candidate = _openaire_str(w)
                        if candidate.startswith("http"):
                            url = candidate
                            break
                    if url:
                        break
            if not url:
                continue

            abstract = _openaire_str(meta.get("description", ""))[:1500]
            date = _openaire_str(meta.get("dateofacceptance", ""))[:10]
            creators = meta.get("creator", [])
            if not isinstance(creators, list):
                creators = [creators]
            authors = [_openaire_str(c) for c in creators[:3]]

            articles.append(
                Article(
                    title=title.strip(),
                    url=url,
                    source="OpenAIRE",
                    abstract=abstract,
                    date=date or _today_str(),
                    authors=authors,
                    doi=doi,
                )
            )
    except Exception as e:
        print(f"[OpenAIRE] Error: {e}")
    return articles


# ── Main ───────────────────────────────────────────────────────────────────


def fetch_all() -> list[Article]:
    print("[fetch] PubMed...")
    pubmed = fetch_pubmed()
    print(f"  → {len(pubmed)} articles")

    time.sleep(1)
    print("[fetch] Semantic Scholar...")
    ss = fetch_semantic_scholar()
    print(f"  → {len(ss)} articles")

    time.sleep(2)
    print("[fetch] Psychedelic Alpha...")
    pa = fetch_psychedelic_alpha()
    print(f"  → {len(pa)} articles")

    time.sleep(1)
    print("[fetch] DiVA...")
    diva = fetch_diva()
    print(f"  → {len(diva)} articles")

    time.sleep(2)
    print("[fetch] Europe PMC...")
    epmc = fetch_europe_pmc()
    print(f"  → {len(epmc)} articles")

    time.sleep(3)
    print("[fetch] EU Clinical Trials Register...")
    euctr = fetch_euctr()
    print(f"  → {len(euctr)} articles")

    time.sleep(2)
    print("[fetch] EMCDDA...")
    emcdda = fetch_emcdda()
    print(f"  → {len(emcdda)} articles")

    time.sleep(3)
    print("[fetch] DART-Europe...")
    dart = fetch_dart_europe()
    print(f"  → {len(dart)} articles")

    time.sleep(2)
    print("[fetch] OpenAIRE...")
    openaire = fetch_openaire()
    print(f"  → {len(openaire)} articles")

    all_articles = pubmed + ss + pa + diva + epmc + euctr + emcdda + dart + openaire
    all_articles = [a for a in all_articles if a.url and a.title]

    # Deduplicate: DOI first (catches cross-source duplicates), then URL
    seen_dois: set[str] = set()
    seen_urls: set[str] = set()
    deduped: list[Article] = []
    for a in all_articles:
        if a.doi:
            if a.doi in seen_dois:
                continue
            seen_dois.add(a.doi)
        if a.url in seen_urls:
            continue
        seen_urls.add(a.url)
        deduped.append(a)

    removed = len(all_articles) - len(deduped)
    if removed:
        print(f"  → dedup removed {removed} cross-source duplicates")
    return deduped
