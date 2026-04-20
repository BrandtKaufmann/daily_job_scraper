"""Entry point: scrape each source, dedup against seen-store, and email a digest."""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys

from .config import load
from .emailer import send_job_digest
from .scrapers.apple import AppleScraper
from .scrapers.base import BaseScraper, Job
from .scrapers.google import GoogleScraper
from .scrapers.riot import RiotScraper
from .seen_store import SeenStore

log = logging.getLogger("djs")

SCRAPERS: list[BaseScraper] = [AppleScraper(), GoogleScraper(), RiotScraper()]
EXCLUDED_TITLE_RE = re.compile(
    r"\b(princip(?:al|le)|senior|sr\.?|director|staff|lead|manager)\b",
    re.IGNORECASE,
)
US_LOCATION_RE = re.compile(r"\b(usa|u\.s\.a\.|united states|us)\b", re.IGNORECASE)


async def _scrape_one(scraper: BaseScraper) -> list[Job]:
    try:
        return await scraper.fetch()
    except Exception:
        log.exception("%s scraper failed", scraper.company)
        return []


def _is_us_location(location: str) -> bool:
    return bool(location and US_LOCATION_RE.search(location))


def _is_filtered_title(title: str) -> bool:
    return bool(title and EXCLUDED_TITLE_RE.search(title))


def _apply_filters(jobs: list[Job]) -> list[Job]:
    kept: list[Job] = []
    removed_title = 0
    removed_location = 0
    for job in jobs:
        if _is_filtered_title(job.title):
            removed_title += 1
            continue
        if not _is_us_location(job.location):
            removed_location += 1
            continue
        kept.append(job)

    log.info(
        "Filtered out %d jobs by title and %d jobs by non-US location",
        removed_title,
        removed_location,
    )
    return kept


async def run(dry_run: bool = False, reset_store: bool = False) -> int:
    results = await asyncio.gather(*(_scrape_one(s) for s in SCRAPERS))
    scraped_jobs: list[Job] = [j for sub in results for j in sub]
    log.info("Scraped %d jobs total", len(scraped_jobs))
    all_jobs = _apply_filters(scraped_jobs)
    log.info("Jobs remaining after filters: %d", len(all_jobs))

    store = SeenStore()
    if reset_store:
        log.warning("Resetting seen-store \u2014 every job will be treated as new.")
        store._seen.clear()  # noqa: SLF001 \u2014 intentional for --reset-store

    new_jobs = store.filter_new(all_jobs)
    log.info("New (unseen) jobs: %d", len(new_jobs))
    for j in new_jobs:
        log.info("  [%s] %s \u2014 %s (%s)", j.company, j.title, j.location, j.posted_date or "?")

    if dry_run:
        log.info("Dry-run: skipping email send and not persisting seen-store.")
        return len(new_jobs)

    cfg = load()
    send_job_digest(new_jobs, cfg)
    store.save()
    return len(new_jobs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily job scraper \u2014 Apple + Google + Riot DS/AI")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scrape and log results without sending email or persisting the seen-store.",
    )
    parser.add_argument(
        "--reset-store", action="store_true",
        help="Treat every scraped job as new (for first run / testing).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug-level logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    count = asyncio.run(run(dry_run=args.dry_run, reset_store=args.reset_store))
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
