"""Relevance filtering for the NPV thesis prize."""

import json
import os
import time

import anthropic

from fetch_theses import Thesis

MODEL = "claude-haiku-4-5-20251001"
MAX_THESES_PER_RUN = 5

FILTER_PROMPT = """\
Du är i juryn för NPV:s uppsatspris (Nätverket för Psykedelisk Vetenskap).

NPV delar varje år ut ett pris till den bästa svenska student-uppsatsen (kandidat eller master) inom psykedelisk vetenskap.

Bedöm om följande uppsats är en potentiell kandidat till priset.

KRITERIER:
- Ska vara en student-uppsats (kandidat-, master-, eller licentiatuppsats)
- Ska behandla psykedelika, psykedelisk-assisterad terapi, relaterad neurovetenskap, harm reduction eller besläktade ämnen
- Hellre svensk institution men inte ett krav
- Empiriska studier, litteraturöversikter och teoriorienterade uppsatser alla OK

INTE relevant:
- Doktorsavhandlingar (för hög nivå för priset)
- Uppsatser som bara tangerar ämnet utan psykedelika som fokus
- Icke-akademiska texter

Uppsats:
Titel: {title}
Källa: {source}
Institution: {institution}
Nivå: {level}
Sammanfattning: {abstract}

Svara ENBART med JSON:
{{"relevant": true/false, "reason": "kort motivering på svenska", "relevance_score": 1-5, "level_guess": "kandidat/master/licentiat/okänt"}}"""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def _truncate(text: str, max_chars: int = 1200) -> str:
    return text[:max_chars] + "…" if len(text) > max_chars else text


def filter_thesis(client: anthropic.Anthropic, thesis: Thesis) -> dict:
    prompt = FILTER_PROMPT.format(
        title=thesis.title,
        source=thesis.source,
        institution=thesis.institution or "okänd",
        level=thesis.level or "okänd",
        abstract=_truncate(thesis.abstract or "Ingen sammanfattning tillgänglig."),
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
        print(f"  [filter_thesis] Error for '{thesis.title[:60]}': {e}")
        return {"relevant": False, "reason": "Fel vid bedömning", "relevance_score": 1, "level_guess": "okänt"}


def process_theses(theses: list[Thesis]) -> list[dict]:
    """
    Filters theses for prize relevance.
    Returns list of dicts: thesis, relevance_score, reason, level_guess.
    Capped at MAX_THESES_PER_RUN.
    """
    client = _client()
    relevant: list[dict] = []

    print(f"[filter_theses] Bedömer {len(theses)} uppsatser...")
    for i, thesis in enumerate(theses):
        print(f"  [{i+1}/{len(theses)}] {thesis.title[:70]}")
        result = filter_thesis(client, thesis)
        print(f"    → relevant={result.get('relevant')}, score={result.get('relevance_score')}, {result.get('reason', '')[:80]}")
        if result.get("relevant"):
            relevant.append(
                {
                    "thesis": thesis,
                    "relevance_score": result.get("relevance_score", 3),
                    "reason": result.get("reason", ""),
                    "level_guess": result.get("level_guess", "okänt"),
                }
            )
        if i < len(theses) - 1:
            time.sleep(0.5)

    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    return relevant[:MAX_THESES_PER_RUN]
