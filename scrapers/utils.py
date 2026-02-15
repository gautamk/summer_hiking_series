"""Shared utilities for WTA scrapers."""

import asyncio
import csv
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, Playwright

AUTH_FILE = Path(__file__).parent.parent / "playwright" / ".auth" / "wta.json"
RAW_DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def csv_path(prefix: str) -> Path:
    """Return a timestamped path under data/raw/, e.g. data/raw/wta_hikes_20260215.csv"""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return RAW_DATA_DIR / f"{prefix}_{date_str}.csv"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a list of dicts to a CSV file with consistent quoting and UTF-8 encoding."""
    if not rows:
        print(f"No rows to write to {path}")
        return

    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {path}")


def scraped_at() -> str:
    """Return current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Playwright browser/context setup
# ---------------------------------------------------------------------------

async def new_context(p: Playwright, headless: bool = True) -> BrowserContext:
    """
    Launch a Chromium browser and return an authenticated context.

    Loads saved storage state from playwright/.auth/wta.json if it exists.
    Run `uv run scrapers/auth.py` first to generate that file.
    """
    browser = await p.chromium.launch(headless=headless)

    if AUTH_FILE.exists():
        context = await browser.new_context(storage_state=str(AUTH_FILE))
        print(f"Loaded auth state from {AUTH_FILE}")
    else:
        context = await browser.new_context()
        print(
            f"Warning: no auth state found at {AUTH_FILE}. "
            "Run `uv run scrapers/auth.py` first to log in."
        )

    return context


async def verify_auth(page: Page) -> bool:
    """
    Probe WTA to confirm the loaded session is still authenticated.

    Navigates to a members-only page and checks whether we land on a login
    redirect. Returns True if the session is valid, False if it has expired.

    Call this once after new_context() before starting a scrape run.
    """
    probe_url = "https://www.wta.org/@@user-account"
    await page.goto(probe_url, wait_until="domcontentloaded")

    # WTA redirects unauthenticated requests to /login
    if "login" in page.url:
        print(
            "Session has expired. "
            "Run `uv run scrapers/auth.py` to log in again."
        )
        return False

    print("Session is valid — proceeding with authenticated scrape.")
    return True


# ---------------------------------------------------------------------------
# Polite crawl delays
# ---------------------------------------------------------------------------

async def polite_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    """Sleep for a random interval to avoid hammering the server."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)


async def pagination_delay(page_num: int) -> None:
    """
    Delay between paginated requests.

    Keeps a short base delay between pages. Every 20 pages takes an extra
    pause to avoid sustained crawl detection.
    """
    delay = random.uniform(1.0, 2.5)
    if page_num > 0 and page_num % 20 == 0:
        delay += random.uniform(5.0, 10.0)
    await asyncio.sleep(delay)
