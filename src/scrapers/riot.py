"""Scraper for Riot Games careers (Data craft, Los Angeles office)."""
from __future__ import annotations

import logging
import re

from playwright.async_api import async_playwright

from .base import BaseScraper, Job

log = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.riotgames.com/en/work-with-us/jobs"
    "#craft=data&office=884&officeName=Los%20Angeles%2C%20USA"
)

_JOB_ID_RE = re.compile(r"/en/j/(\d+)")

KEYWORDS = re.compile(
    r"\b(data scientist|machine learning|\bml\b|\bai\b|artificial intelligence|"
    r"deep learning|data science|data engineer|research scientist|researcher|"
    r"applied scientist|generative ai|llm|insights|analytics)\b",
    re.IGNORECASE,
)


class RiotScraper(BaseScraper):
    company = "Riot Games"

    async def fetch(self) -> list[Job]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()
            log.info("Riot: loading %s", SEARCH_URL)
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=60_000)

            try:
                await page.wait_for_selector('a[href*="/en/j/"]', timeout=30_000)
            except Exception:
                log.warning("Riot: job links did not appear; returning 0")
                await browser.close()
                return []

            raw = await page.evaluate(
                """() => {
                    const seen = new Set();
                    const rows = [];
                    for (const a of document.querySelectorAll('a[href*="/en/j/"]')) {
                        const href = a.getAttribute("href");
                        const text = a.innerText ? a.innerText.trim() : "";
                        if (!href || !text || seen.has(href)) continue;
                        seen.add(href);
                        rows.push({ href, text });
                    }
                    return rows;
                }"""
            )
            await browser.close()

        jobs: list[Job] = []
        for r in raw:
            href = r.get("href") or ""
            text = r.get("text") or ""
            url = _normalize_url(href)
            job_id = _extract_job_id(url)
            if not job_id:
                continue

            parsed = _parse_listing_text(text)
            if not parsed["title"]:
                continue
            title = parsed["title"]
            if not KEYWORDS.search(title):
                continue

            jobs.append(
                Job(
                    company=self.company,
                    job_id=job_id,
                    title=title,
                    location=parsed["location"],
                    url=url,
                    posted_date=None,
                    team=parsed["team"],
                )
            )

        log.info("Riot: parsed %d jobs", len(jobs))
        return jobs


def _normalize_url(href: str) -> str:
    href = href.strip()
    if href.startswith("http"):
        return href
    return f"https://www.riotgames.com{href}"


def _extract_job_id(url: str) -> str | None:
    m = _JOB_ID_RE.search(url)
    if not m:
        return None
    return m.group(1)


def _parse_listing_text(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line and line.strip()]
    if not lines:
        return {"title": "", "location": "", "team": ""}

    title = lines[0]
    location = lines[-1] if len(lines) > 1 else ""
    team_parts = lines[1:-1]
    team = " | ".join(team_parts) if team_parts else ""
    return {"title": title, "location": location, "team": team}
