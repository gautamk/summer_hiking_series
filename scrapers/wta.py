"""
WTA hike info scraper.

Scrapes trail metadata from wta.org and writes to data/raw/wta_hikes_<date>.csv.

Usage:
    # Scrape a single trail (for development/testing):
    uv run scrapers/wta.py --trail-url https://www.wta.org/go-hiking/hikes/mt-si

    # Scrape all hikes from the WTA hiking guide (default):
    uv run scrapers/wta.py

Prerequisites:
    Run `uv run scrapers/auth.py` first to save a logged-in session.
"""

import argparse
import asyncio
from typing import Any

from playwright.async_api import Page, async_playwright

from scrapers.utils import csv_path, new_context, polite_delay, scraped_at, verify_auth, write_csv

# WTA hiking guide listing URL — sorted by rating so popular hikes come first
WTA_HIKE_LIST_URL = "https://www.wta.org/go-hiking/hikes?sort=rating"


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

async def scrape_hike_detail(page: Page, url: str) -> dict[str, Any]:
    """Scrape all available metadata from a single WTA trail detail page."""
    await page.goto(url, wait_until="domcontentloaded")
    await polite_delay()

    record: dict[str, Any] = {
        "trail_name": None,
        "location": None,
        "distance_miles": None,
        "elevation_gain_ft": None,
        "highest_point_ft": None,
        "difficulty": None,
        "trail_type": None,  # out-and-back, loop, etc.
        "required_pass": None,
        "dogs_allowed": None,
        "kid_friendly": None,
        "season_window": None,
        "highlight": None,
        "wta_url": url,
        "source": "wta",
        "scraped_at": scraped_at(),
    }

    # Trail name
    name_el = page.locator("h1.documentFirstHeading")
    if await name_el.count():
        record["trail_name"] = (await name_el.first.text_content() or "").strip()

    # Stats block — WTA uses a consistent list of stat items
    stat_items = page.locator(".hike-stat")
    count = await stat_items.count()
    for i in range(count):
        item = stat_items.nth(i)
        label_el = item.locator(".title")
        value_el = item.locator(".hike-stat__content, span:not(.title)")

        label = (await label_el.text_content() or "").strip().lower()
        value = (await value_el.first.text_content() or "").strip() if await value_el.count() else ""

        if "distance" in label:
            # e.g. "5.0 miles, roundtrip"
            parts = value.split(",")
            try:
                record["distance_miles"] = float(parts[0].replace("miles", "").strip())
            except ValueError:
                record["distance_miles"] = value
            if len(parts) > 1:
                record["trail_type"] = parts[1].strip()
        elif "gain" in label or "elevation" in label:
            try:
                record["elevation_gain_ft"] = int(value.replace(",", "").replace("feet", "").strip())
            except ValueError:
                record["elevation_gain_ft"] = value
        elif "highest" in label:
            try:
                record["highest_point_ft"] = int(value.replace(",", "").replace("feet", "").strip())
            except ValueError:
                record["highest_point_ft"] = value
        elif "difficulty" in label:
            record["difficulty"] = value
        elif "pass" in label or "permit" in label:
            record["required_pass"] = value

    # Dogs and kid-friendly tags
    features = page.locator(".hike-features .feature")
    features_count = await features.count()
    feature_texts = []
    for i in range(features_count):
        t = (await features.nth(i).text_content() or "").strip().lower()
        feature_texts.append(t)
    record["dogs_allowed"] = "dogs allowed on leash" in feature_texts or "dogs allowed" in feature_texts
    record["kid_friendly"] = "kid friendly" in feature_texts or "good for kids" in feature_texts

    # Location / region
    region_el = page.locator(".hike-region a, .region-breadcrumb a")
    if await region_el.count():
        record["location"] = (await region_el.first.text_content() or "").strip()

    # Highlight / description teaser (first sentence of the trail description)
    desc_el = page.locator("#hike-body-text p, .hike-description p")
    if await desc_el.count():
        full_text = (await desc_el.first.text_content() or "").strip()
        sentences = full_text.split(".")
        record["highlight"] = sentences[0].strip() + ("." if len(sentences) > 1 else "")

    # Best season / season window (sometimes in the description or a sidebar)
    season_el = page.locator(".hike-season, .best-season")
    if await season_el.count():
        record["season_window"] = (await season_el.first.text_content() or "").strip()

    return record


async def get_hike_urls(page: Page, max_pages: int = 20) -> list[str]:
    """
    Collect hike detail URLs from WTA's paginated hiking guide listing.

    Iterates through listing pages up to max_pages and returns all unique
    trail URLs found.
    """
    urls: list[str] = []
    current_url = WTA_HIKE_LIST_URL
    page_num = 0

    while current_url and page_num < max_pages:
        print(f"  Fetching listing page {page_num + 1}: {current_url}")
        await page.goto(current_url, wait_until="domcontentloaded")
        await polite_delay()

        # Hike links on listing pages
        links = page.locator("a.listitem-title")
        count = await links.count()
        for i in range(count):
            href = await links.nth(i).get_attribute("href")
            if href and "/go-hiking/hikes/" in href:
                full = href if href.startswith("http") else f"https://www.wta.org{href}"
                if full not in urls:
                    urls.append(full)

        # Pagination — look for a "next" link
        next_link = page.locator("a[title='Next']")
        if await next_link.count():
            next_href = await next_link.first.get_attribute("href")
            current_url = next_href if next_href and next_href.startswith("http") else (
                f"https://www.wta.org{next_href}" if next_href else None
            )
        else:
            current_url = None

        page_num += 1

    print(f"Found {len(urls)} hike URLs across {page_num} listing page(s).")
    return urls


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(trail_url: str | None = None) -> None:
    async with async_playwright() as p:
        context = await new_context(p, headless=True)
        page = await context.new_page()

        if not await verify_auth(page):
            await context.close()
            return

        if trail_url:
            print(f"Single-trail mode: {trail_url}")
            hike_urls = [trail_url]
        else:
            print("Collecting hike URLs from WTA hiking guide...")
            hike_urls = await get_hike_urls(page)

        rows: list[dict[str, Any]] = []
        for i, url in enumerate(hike_urls, 1):
            print(f"[{i}/{len(hike_urls)}] Scraping: {url}")
            try:
                row = await scrape_hike_detail(page, url)
                rows.append(row)
                print(f"  -> {row.get('trail_name', 'unknown')}")
            except Exception as exc:
                print(f"  ERROR scraping {url}: {exc}")

        await context.close()

    out_path = csv_path("wta_hikes")
    write_csv(out_path, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="WTA hike info scraper")
    parser.add_argument(
        "--trail-url",
        metavar="URL",
        help="Scrape a single trail URL (for development/testing)",
    )
    args = parser.parse_args()
    asyncio.run(run(trail_url=args.trail_url))


if __name__ == "__main__":
    main()
