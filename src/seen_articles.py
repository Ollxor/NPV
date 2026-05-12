import hashlib
import json
import os
from datetime import datetime, timezone

SEEN_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "seen.json")


def _load() -> dict:
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": [], "last_updated": ""}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def article_hash(url: str) -> str:
    return "sha256:" + hashlib.sha256(url.strip().encode()).hexdigest()


def is_seen(url: str) -> bool:
    data = _load()
    return article_hash(url) in data["seen"]


def mark_seen(urls: list[str]) -> None:
    data = _load()
    seen_set = set(data["seen"])
    for url in urls:
        seen_set.add(article_hash(url))
    data["seen"] = sorted(seen_set)
    _save(data)
