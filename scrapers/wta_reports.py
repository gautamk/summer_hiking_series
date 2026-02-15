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

from scrapers.utils import csv_path, new_context, pagination_delay, polite_delay, scraped_at, verify_auth, write_csv

DEFAULT_DAYS = 90


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def _cutoff_date(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _parse_report_date(title_text: str) -> str:
    """
    Extract the date string from a WTA report title link.

    Title format: "Trail Name — Month DD, YYYY"
    Returns the date portion as a string, e.g. "Feb. 12, 2026".
    """
    if "—" in title_text:
        return title_text.split("—", 1)[1].strip()
    return title_text.strip()


def _parse_date_dt(date_str: str) -> datetime | None:
    """Parse a WTA date string into a timezone-aware datetime."""
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


async def scrape_reports_for_trail(
    page: Page,
    trail_url: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """
    Scrape trip reports from a single trail's WTA page.

    WTA loads reports into #reports_target on the trail page (5 per page).
    Pagination uses @@related_tripreport_listing?b_start:int=N URLs.
    Stops paginating once report dates fall before the cutoff.
    """
    await page.goto(trail_url, wait_until="domcontentloaded")
    await polite_delay()

    rows: list[dict[str, Any]] = []
    page_num = 0

    while True:
        # Wait for report items — retry once on timeout to handle slow loads
        loaded = False
        for attempt in range(2):
            try:
                await page.wait_for_selector("#trip-reports .item", timeout=12000)
                loaded = True
                break
            except Exception:
                if attempt == 0:
                    print(f"    page {page_num + 1}: slow load, waiting and retrying…")
                    await polite_delay(3.0, 6.0)

        if not loaded:
            print(f"    page {page_num + 1}: timed out waiting for reports — stopping pagination")
            break

        report_els = page.locator("#trip-reports .item")
        count = await report_els.count()
        if count == 0:
            break

        print(f"    page {page_num + 1}: {count} report(s)")

        past_cutoff = False
        for i in range(count):
            el = report_els.nth(i)

            # Date: extracted from title link text "Trail Name — Feb. 12, 2026"
            title_text = (await el.locator(".listitem-title a").first.text_content() or "").strip()
            report_date_raw = _parse_report_date(title_text)
            report_dt = _parse_date_dt(report_date_raw)

            if report_dt and report_dt < cutoff:
                past_cutoff = True
                continue  # keep checking in case page has out-of-order dates

            # Author: .wta-icon-headline__text
            author_el = el.locator(".wta-icon-headline__text")
            author = ""
            if await author_el.count():
                author = (await author_el.first.text_content() or "").strip()

            # Conditions: .trail-issues text, strip the "Beware of:" label
            conditions_el = el.locator(".trail-issues")
            conditions = ""
            if await conditions_el.count():
                raw = (await conditions_el.first.text_content() or "").strip()
                # Remove the "Beware of:" prefix if present
                conditions = raw.replace("Beware of:", "").strip()

            # Report body text: full text if present, else excerpt
            text_el = el.locator(".trip-report-full-text, .trip-report-excerpt")
            text_summary = ""
            if await text_el.count():
                text_summary = (await text_el.first.text_content() or "").strip()

            rows.append({
                "trail_url": trail_url,
                "report_date": report_date_raw,
                "author": author,
                "conditions": conditions,
                "snow_level": "",  # WTA does not expose a separate snow field in listings
                "text_summary": text_summary,
                "source": "wta",
                "scraped_at": scraped_at(),
            })

        if past_cutoff:
            break  # all remaining pages are older than cutoff

        # Pagination: nav.pagination is a sibling of #trip-reports inside .js-tab-target
        # These links go to @@related_tripreport_listing?b_start:int=N
        next_link = page.locator("nav.pagination li.next a")
        if not await next_link.count():
            break  # last page

        next_href = await next_link.first.get_attribute("href")
        if not next_href:
            break

        next_full = next_href if next_href.startswith("http") else f"https://www.wta.org{next_href}"
        page_num += 1
        await pagination_delay(page_num)
        await page.goto(next_full, wait_until="domcontentloaded")

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
