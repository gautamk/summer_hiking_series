# Task Tracker

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` cancelled

---

## Phase 1 — Project Skeleton

- [x] Create directory structure (`scrapers/`, `db/`, `db/migrations/`, `data/raw/`, `data/processed/`, `ui/`, `ui/templates/`, `ui/dist/`)
- [x] Initialise `pyproject.toml` with `uv init` and add initial deps: `playwright`
- [x] Run `uv run playwright install` to download browser binaries
- [x] Add `.gitignore` entries for `hiking.db`, `data/raw/`, `ui/dist/`, `__pycache__/`, `.venv/`
- [x] Verify all scripts can be invoked with `uv run <script>`

---

## Phase 2 — Scrapers

> Scrape real data first so the DB schema is grounded in actual field names and types.

### 2a. Scraper Shared Utilities
- [ ] Write `scrapers/utils.py` with shared helpers:
  - CSV writer with consistent quoting and encoding
  - Playwright browser/context setup (shared async context, sensible defaults)
  - Polite crawl delays between page loads
  - `scraped_at` timestamp injection

### 2b. WTA Hike Info Scraper
- [ ] Write `scrapers/wta.py` to scrape trail metadata from WTA
  - Output: `data/raw/wta_hikes_<date>.csv`
  - Capture all fields WTA exposes; do not pre-filter — schema is derived from output
- [ ] Handle rate limiting and polite crawl delays
- [ ] Add `--trail-url` flag for single-trail scrape during development
- [ ] Produce at least one real CSV output file in `data/raw/` before proceeding to Phase 3

### 2c. WTA Trip Report Scraper
- [ ] Write `scrapers/wta_reports.py` to scrape recent trip reports per trail
  - Output: `data/raw/wta_reports_<date>.csv`
  - Capture all fields WTA exposes; do not pre-filter — schema is derived from output
- [ ] Limit to reports from the last 60 days by default (`--days` flag to override)
- [ ] Produce at least one real CSV output file in `data/raw/` before proceeding to Phase 3

---

## Phase 3 — DB Schema (derived from scraped CSVs)

> Design the schema after inspecting real scraper output — not before.

- [ ] Inspect `data/raw/` CSVs and document actual field names, types, and sample values
- [ ] Design and write initial SQL schema (`db/migrations/001_initial.sql`)
  - Tables: `hikes`, `trip_reports`, `schedule`
  - Column names and types based on actual scraped data
  - Include `source`, `scraped_at`, `updated_at` traceability columns

---

## Phase 4 — DB Module

- [ ] Write `db/manage.py` with subcommands:
  - `migrate` — apply pending migration files in order
  - `import <csv_file>` — import a CSV into the appropriate table
  - `status` — show current schema version and row counts
- [ ] Implement conflict resolution on import:
  - Default: newer `scraped_at` wins for all fields
  - Document how to override per-field in CLAUDE.md
- [ ] Write migration runner that tracks applied migrations in `schema_version` table
- [ ] Write tests for import and conflict resolution (`db/tests/`)

---

## Phase 5 — UI Module

- [ ] Write `ui/build.py` to generate static HTML from `hiking.db`
  - Reads all hikes and their latest trip reports
  - Generates `ui/dist/index.html`
- [ ] Design layout sections:
  - Weekend schedule (date, trail name, difficulty, pass required)
  - Trail detail cards (expandable, with latest trip report summary)
  - Season filter (Spring / Summer / Fall)
  - Sort controls (by distance, elevation, drive time)
- [ ] Port existing `index.html` content and styling into the template
- [ ] Add `ui/templates/` directory for HTML template fragments
- [ ] Verify generated output matches (or improves on) current `index.html`

---

## Phase 6 — Migration from Current Data

- [ ] Convert existing CSVs in `2026/data/` to new schema format
  - Add `source`, `scraped_at` columns (backfill with `manual` / today's date)
- [ ] Import converted CSVs into `hiking.db` via `db/manage.py import`
- [ ] Verify all 40 weekends and 120+ trails are present in DB
- [ ] Regenerate `index.html` via `ui/build.py` and confirm parity with existing

---

## Phase 7 — Housekeeping

- [ ] Update `README.md` to reflect new architecture
- [ ] Document how to run each module end-to-end using `uv run`
- [ ] Add a top-level `Makefile` with targets: `scrape`, `import`, `build`, `all` (each delegating to `uv run`)

---

## Backlog / Future

- [ ] AllTrails scraper (lower priority; WTA is primary source)
- [ ] Scheduled scraping via GitHub Actions (cron)
- [ ] Trip report freshness indicator in UI (highlight stale trails)
- [ ] Export to iCal / Google Calendar format from schedule table
