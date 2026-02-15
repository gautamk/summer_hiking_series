"""
WTA trip report scraper.

Scrapes recent trip reports per trail from wta.org and writes to
data/raw/wta_reports_<date>.csv.

Usage:
    # Scrape reports for a single trail (for development/testing):
    uv run scrapers/wta_reports.py --trail-url https://www.wta.org/go-hiking/hikes/mt-si

    # Scrape reports for all hikes in a previously scraped hikes CSV:
    uv run scrapers/wta_reports.py --hikes-csv data/raw/wta_hikes_20260215.csv

    # Override the default 60-day lookback window:
    uv run scrapers/wta_reports.py --trail-url <URL> --days 30

Prerequisites:
    Run `uv run scrapers/auth.py` first to save a logged-in session.
"""

import argparse
import asyncio
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from scrapers.utils import csv_path, new_context, polite_delay, scraped_at, verify_auth, write_csv

DEFAULT_DAYS = 60


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def _cutoff_date(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def scrape_reports_for_trail(
    page: Page,
    trail_url: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """
    Scrape trip reports from a single trail's WTA page.

    Returns a list of report dicts. Stops paginating once report dates fall
    before the cutoff.
    """
    # WTA trip reports live on the trail page under the #trip-reports anchor
    reports_url = trail_url.rstrip("/") + "#trip-reports"
    await page.goto(trail_url, wait_until="domcontentloaded")
    await polite_delay()

    rows: list[dict[str, Any]] = []
    page_num = 0
    current_url = trail_url

    while True:
        # Wait for report items to appear (or proceed if none present)
        try:
            await page.wait_for_selector(".trip-report-list-item, .trip-report", timeout=5000)
        except Exception:
            break  # no reports on this page

        report_els = page.locator(".trip-report-list-item, .trip-report")
        count = await report_els.count()
        if count == 0:
            break

        past_cutoff = False
        for i in range(count):
            el = report_els.nth(i)

            # Report date
            date_el = el.locator("time, .report-date, .date")
            report_date_raw = ""
            if await date_el.count():
                report_date_raw = (
                    await date_el.first.get_attribute("datetime")
                    or await date_el.first.text_content()
                    or ""
                ).strip()

            # Parse date for cutoff comparison
            report_dt: datetime | None = None
            for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
                try:
                    report_dt = datetime.strptime(report_date_raw[:10], fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

            if report_dt and report_dt < cutoff:
                past_cutoff = True
                continue  # skip this report; keep checking in case dates are out of order

            # Author
            author_el = el.locator(".report-author, .author, .username")
            author = ""
            if await author_el.count():
                author = (await author_el.first.text_content() or "").strip()

            # Conditions summary (short label — e.g. "Trail in good condition")
            conditions_el = el.locator(".report-conditions, .conditions, .trail-conditions")
            conditions = ""
            if await conditions_el.count():
                conditions = (await conditions_el.first.text_content() or "").strip()

            # Snow level
            snow_el = el.locator(".snow-level, .snow, [class*='snow']")
            snow_level = ""
            if await snow_el.count():
                snow_level = (await snow_el.first.text_content() or "").strip()

            # Report body text
            body_el = el.locator(".report-text, .report-body, p")
            text_summary = ""
            if await body_el.count():
                text_summary = (await body_el.first.text_content() or "").strip()

            rows.append({
                "trail_url": trail_url,
                "report_date": report_date_raw,
                "author": author,
                "conditions": conditions,
                "snow_level": snow_level,
                "text_summary": text_summary,
                "source": "wta",
                "scraped_at": scraped_at(),
            })

        if past_cutoff:
            break  # all remaining reports are older than cutoff

        # Pagination within trip reports
        next_link = page.locator(".pager-next a, a[title='Next']")
        if await next_link.count():
            next_href = await next_link.first.get_attribute("href")
            if next_href:
                next_full = next_href if next_href.startswith("http") else f"https://www.wta.org{next_href}"
                await page.goto(next_full, wait_until="domcontentloaded")
                await polite_delay()
                page_num += 1
                continue
        break

    return rows


def load_trail_urls_from_csv(csv_file: Path) -> list[str]:
    """Read wta_url column from a previously scraped hikes CSV."""
    urls = []
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("wta_url", "").strip()
            if url:
                urls.append(url)
    return urls


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(
    trail_url: str | None = None,
    hikes_csv: Path | None = None,
    days: int = DEFAULT_DAYS,
) -> None:
    cutoff = _cutoff_date(days)
    print(f"Scraping trip reports from the last {days} days (since {cutoff.date()}).")

    if trail_url:
        trail_urls = [trail_url]
    elif hikes_csv:
        trail_urls = load_trail_urls_from_csv(hikes_csv)
        print(f"Loaded {len(trail_urls)} trail URLs from {hikes_csv}")
    else:
        print("Error: provide --trail-url or --hikes-csv")
        return

    all_rows: list[dict[str, Any]] = []

    async with async_playwright() as p:
        context = await new_context(p, headless=True)
        page = await context.new_page()

        if not await verify_auth(page):
            await context.close()
            return

        for i, url in enumerate(trail_urls, 1):
            print(f"[{i}/{len(trail_urls)}] Reports for: {url}")
            try:
                rows = await scrape_reports_for_trail(page, url, cutoff)
                print(f"  -> {len(rows)} report(s) found")
                all_rows.extend(rows)
            except Exception as exc:
                print(f"  ERROR scraping {url}: {exc}")

        await context.close()

    out_path = csv_path("wta_reports")
    write_csv(out_path, all_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="WTA trip report scraper")
    parser.add_argument(
        "--trail-url",
        metavar="URL",
        help="Scrape reports for a single trail URL (for development/testing)",
    )
    parser.add_argument(
        "--hikes-csv",
        metavar="FILE",
        type=Path,
        help="Path to a wta_hikes CSV; scrapes reports for all trails in it",
    )
    parser.add_argument(
        "--days",
        metavar="N",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Only include reports from the last N days (default: {DEFAULT_DAYS})",
    )
    args = parser.parse_args()

    if not args.trail_url and not args.hikes_csv:
        parser.error("Provide --trail-url or --hikes-csv")

    asyncio.run(run(trail_url=args.trail_url, hikes_csv=args.hikes_csv, days=args.days))


if __name__ == "__main__":
    main()
