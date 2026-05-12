"""NPV Omvärldsbevakning — entry point."""

import os
import sys

from fetch_sources import fetch_all
from filter_and_summarize import process_articles
from post_to_slack import post_article, post_error, post_summary
from seen_articles import is_seen, mark_seen


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        print("=" * 60)
        print("DRY RUN — inget postas till Slack")
        print("=" * 60)

    # 1. Fetch
    print("\n── Hämtar artiklar ──────────────────────────────────────")
    try:
        all_articles = fetch_all()
    except Exception as e:
        print(f"Kritiskt fel vid hämtning: {e}")
        post_error(str(e), dry_run=dry_run)
        sys.exit(1)

    print(f"Totalt hämtade: {len(all_articles)}")

    # 2. Deduplication
    new_articles = [a for a in all_articles if not is_seen(a.url)]
    skipped = len(all_articles) - len(new_articles)
    print(f"Nya (ej sedda): {len(new_articles)} · Redan sedda: {skipped}")

    if not new_articles:
        print("Inga nya artiklar — postar statusmeddelande.")
        post_summary(
            total=len(all_articles),
            relevant=0,
            skipped=skipped,
            dry_run=dry_run,
        )
        return

    # 3. Filter + generate FB posts
    print("\n── Filtrerar och genererar FB-texter ────────────────────")
    relevant_items = process_articles(new_articles)
    print(f"Relevanta efter filtrering: {len(relevant_items)}")

    # 4. Post to Slack
    print("\n── Postar till Slack ─────────────────────────────────────")
    for item in relevant_items:
        print(f"  Postar: {item['article'].title[:70]}")
        post_article(item, dry_run=dry_run)

    post_summary(
        total=len(all_articles),
        relevant=len(relevant_items),
        skipped=skipped,
        dry_run=dry_run,
    )

    # 5. Mark all fetched articles as seen (not just relevant ones)
    if not dry_run:
        mark_seen([a.url for a in all_articles])
        print(f"Markerade {len(all_articles)} artiklar som sedda.")
    else:
        print("[DRY RUN] Markerar inte artiklar som sedda.")

    print("\nKlart.")


if __name__ == "__main__":
    main()
