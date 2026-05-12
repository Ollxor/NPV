"""Fetches student theses from DiVA and SwePub, limited to the current prize year."""

import time
from dataclasses import dataclass, field
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NPV-UpsatsPrisBot/1.0; "
        "+https://github.com/Ollxor/NPV)"
    )
}

PRIZE_YEAR = datetime.utcnow().year  # Uppsatser från innevarande år söks löpande

# DiVA: student theses only, sorted by date
DIVA_THESES_URL = (
    "https://www.diva-portal.org/smash/export.jsf"
    "?format=atom"
    "&query=psilocybin+OR+psilocin+OR+psykedelika+OR+psychedelic"
    "+OR+hallucinogen+OR+mdma+OR+ayahuasca+OR+ketamin"
    "&aq2=%5B%5B%7B%22publicationTypeCode%22%3A%22studentThesis%22%7D%5D%5D"
    "&noOfRows=20&sortOrder=dateSort_sort_desc&onlyFullText=false&sf=all"
)

# SwePub: Swedish academic publications, filter thesis
SWEPUB_URL = (
    "https://swepub.kb.se/api/v1/search"
    "?query=psilocybin+OR+psykedelika+OR+psychedelic+OR+hallucinogen+OR+mdma"
    "&match=freetext&contentType=thesis"
    "&sort=date&sortOrder=desc&offset=0&limit=15"
)


@dataclass
class Thesis:
    title: str
    url: str
    source: str
    abstract: str = ""
    date: str = ""
    authors: list[str] = field(default_factory=list)
    institution: str = ""
    level: str = ""  # kandidat / master / licentiat / doktorsavhandling


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _is_prize_year(date_str: str) -> bool:
    """Returns True if date_str contains the current prize year."""
    return str(PRIZE_YEAR) in date_str


def fetch_diva_theses() -> list[Thesis]:
    theses: list[Thesis] = []
    try:
        r = requests.get(DIVA_THESES_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        for entry in feed.entries[:20]:
            title = entry.get("title", "").strip()
            url = entry.get("link") or entry.get("id", "")
            summary_html = entry.get("summary", "")
            abstract = BeautifulSoup(summary_html, "lxml").get_text()[:800]
            date = entry.get("published", _today_str())[:10]

            # Extract institution and level from tags/categories
            institution = ""
            level = ""
            for tag in entry.get("tags", []):
                term = tag.get("term", "")
                if any(w in term.lower() for w in ["universitet", "högskola", "university"]):
                    institution = term
                if any(w in term.lower() for w in ["kandidat", "master", "licentiat", "doktor"]):
                    level = term

            authors = []
            for a in entry.get("authors", [])[:3]:
                name = a.get("name", "").strip()
                if name:
                    authors.append(name)

            if title and url and _is_prize_year(date):
                theses.append(
                    Thesis(
                        title=title,
                        url=url,
                        source="DiVA",
                        abstract=abstract,
                        date=date,
                        authors=authors,
                        institution=institution,
                        level=level,
                    )
                )
    except Exception as e:
        print(f"[DiVA theses] Error: {e}")
    return theses


def fetch_swepub_theses() -> list[Thesis]:
    theses: list[Thesis] = []
    try:
        r = requests.get(SWEPUB_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", {}).get("hits", []) or data.get("items", []) or []
        for item in hits[:15]:
            source = item.get("_source", item)
            title = ""
            if isinstance(source.get("title"), list):
                title = source["title"][0].get("value", "") if source["title"] else ""
            elif isinstance(source.get("title"), str):
                title = source["title"]

            url = source.get("identifier", {}).get("uri", "") if isinstance(source.get("identifier"), dict) else ""
            if not url:
                for ident in source.get("identifiedBy", []):
                    if ident.get("type") == "URI":
                        url = ident.get("value", "")
                        break
            if not url:
                continue

            abstract = ""
            for ab in source.get("abstract", []):
                if isinstance(ab, dict):
                    abstract = ab.get("value", "")[:800]
                    break

            date = source.get("publicationYear", "") or _today_str()[:4]

            authors = []
            for contrib in source.get("contribution", [])[:3]:
                agent = contrib.get("agent", {})
                name = agent.get("familyName", "")
                given = agent.get("givenName", "")
                if name:
                    authors.append(f"{name} {given}".strip())

            institution = ""
            for org in source.get("publication", [{}]):
                institution = org.get("name", "")
                if institution:
                    break

            level = source.get("contentType", "")

            if title and _is_prize_year(str(date)):
                theses.append(
                    Thesis(
                        title=title,
                        url=url,
                        source="SwePub",
                        abstract=abstract,
                        date=str(date),
                        authors=authors,
                        institution=institution,
                        level=level,
                    )
                )
    except Exception as e:
        print(f"[SwePub] Error: {e}")
    return theses


def fetch_all_theses() -> list[Thesis]:
    print(f"[fetch_theses] Söker uppsatser från {PRIZE_YEAR}...")
    print("[fetch_theses] DiVA...")
    diva = fetch_diva_theses()
    print(f"  → {len(diva)} uppsatser")

    time.sleep(1)
    print("[fetch_theses] SwePub...")
    swepub = fetch_swepub_theses()
    print(f"  → {len(swepub)} uppsatser")

    all_theses = diva + swepub
    return [t for t in all_theses if t.url and t.title]
