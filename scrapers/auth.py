"""
WTA login setup — run once to save authenticated browser state.

Usage:
    uv run scrapers/auth.py

Launches a headed Chromium browser, navigates to the WTA login page, and
waits for you to log in manually. Once logged in, saves the browser storage
state (cookies + localStorage) to playwright/.auth/wta.json so all scrapers
can reuse the session without logging in again.

The saved state is valid until WTA's session cookies expire. Re-run this
script whenever scrapers start getting redirected to the login page.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

AUTH_DIR = Path(__file__).parent.parent / "playwright" / ".auth"
AUTH_FILE = AUTH_DIR / "wta.json"
LOGIN_URL = "https://www.wta.org/login?came_from=/backpack"


async def main() -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"Opening WTA login page: {LOGIN_URL}")
        await page.goto(LOGIN_URL)

        print("\nPlease log in to your WTA account in the browser window.")
        print("When you are fully logged in, return here and press Enter.")
        input("Press Enter after logging in...")

        # Confirm we are actually logged in by checking for a logout link or
        # a user-specific element. WTA shows a user menu when authenticated.
        logged_in = await page.locator("a[href*='logout'], .user-name, #user-menu").count()
        if logged_in == 0:
            print("\nWarning: could not detect a logged-in state.")
            print("If the session looks valid in the browser, you can still save it.")
            confirm = input("Save state anyway? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Aborted. Re-run the script and log in before pressing Enter.")
                await browser.close()
                return

        await context.storage_state(path=str(AUTH_FILE))
        print(f"\nAuth state saved to: {AUTH_FILE}")
        print("Scrapers will now reuse this session automatically.")

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
