# Task Tracker

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` cancelled

---

## Phase 1 — Project Skeleton

- [ ] Create directory structure (`scrapers/`, `db/`, `db/migrations/`, `data/raw/`, `data/processed/`, `ui/`, `ui/dist/`)
- [ ] Add `requirements.txt` with initial deps (requests, beautifulsoup4, lxml)
- [ ] Add `.gitignore` entries for `hiking.db`, `data/raw/`, `ui/dist/`, `__pycache__/`, `.venv/`

---

## Phase 2 — DB Module

- [ ] Design and write initial SQL schema (`db/migrations/001_initial.sql`)
  - Tables: `hikes`, `trip_reports`, `schedule`
  - Include `source`, `scraped_at`, `updated_at` columns on all tables
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

## Phase 3 — Scrapers

### 3a. WTA Hike Info Scraper
- [ ] Write `scrapers/wta.py` to scrape trail metadata from WTA
  - Output: `data/raw/wta_hikes_<date>.csv`
  - Fields: trail_name, location, distance_miles, elevation_gain_ft, difficulty, season_window, required_pass, highlight, wta_url
- [ ] Handle rate limiting and polite crawl delays
- [ ] Add `--trail-url` flag for single-trail scrape during development

### 3b. WTA Trip Report Scraper
- [ ] Write `scrapers/wta_reports.py` to scrape recent trip reports per trail
  - Output: `data/raw/wta_reports_<date>.csv`
  - Fields: hike_id (matched by wta_url), report_date, conditions, snow_level, author, text_summary
- [ ] Limit to reports from the last 60 days by default (`--days` flag to override)

### 3c. Scraper Shared Utilities
- [ ] Write `scrapers/utils.py` with shared helpers:
  - CSV writer with consistent quoting and encoding
  - HTTP session with retry logic and user-agent header
  - `scraped_at` timestamp injection

---

## Phase 4 — UI Module

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

## Phase 5 — Migration from Current Data

- [ ] Convert existing CSVs in `2026/data/` to new schema format
  - Add `source`, `scraped_at` columns (backfill with `manual` / today's date)
- [ ] Import converted CSVs into `hiking.db` via `db/manage.py import`
- [ ] Verify all 40 weekends and 120+ trails are present in DB
- [ ] Regenerate `index.html` via `ui/build.py` and confirm parity with existing

---

## Phase 6 — Housekeeping

- [ ] Update `README.md` to reflect new architecture
- [ ] Document how to run each module end-to-end
- [ ] Add a top-level `Makefile` with targets: `scrape`, `import`, `build`, `all`

---

## Backlog / Future

- [ ] AllTrails scraper (lower priority; WTA is primary source)
- [ ] Scheduled scraping via GitHub Actions (cron)
- [ ] Trip report freshness indicator in UI (highlight stale trails)
- [ ] Export to iCal / Google Calendar format from schedule table
