# Manga Tracker

Manga Tracker helps users track manga/manhwa updates across different websites with automatic latest chapter checks, reading progress sync, and a dashboard for catching up quickly.

## Features

- User authentication (local accounts with hashed passwords)
- Add/remove series by providing title and series listing URL
- Automatic chapter detection from series pages (latest chapter number and label)
- Unread badge (shows how many chapters behind)
- Reading progress via web UI and extension API
- Parallel checks with thread pool
- Scheduled background checks every 30 minutes (configurable)
- Full JSON import/export for backup and migration
- Cover image extraction from meta tags or images
- Site profiles for popular sites (AsuraScans, MangaKatana, ArenaScan, etc.)
- Advanced chapter parsing (heuristics, URL patterns, series slug matching)
- Browser extension API (`/api/series/ensure`, `/api/progress`)
- Debug scrape endpoint with confidence and parser diagnostics
- PostgreSQL support for production (SQLite fallback for local dev)
- Optional Selenium fallback for JavaScript-heavy pages

## Tech Stack

- Backend: Flask, APScheduler, requests, BeautifulSoup4
- Databases: SQLite (default) or PostgreSQL (`psycopg2-binary`)
- Optional scraping runtime: Selenium + ChromeDriver
- Frontend: Jinja templates + custom CSS

## Installation

### 1) Clone the repository

```bash
git clone https://github.com/yourusername/manga-tracker.git
cd manga-tracker
```

### 2) Create virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
# or
venv\Scripts\activate      # Windows
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Configure environment

```bash
# Required in production
export SECRET_KEY="your-very-long-random-secret-key"

# PostgreSQL for persistence on Render
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Optional tuning
export HTTP_TIMEOUT_SECONDS=15
export MAX_CHECK_WORKERS=6
export CHECK_INTERVAL_MINUTES=30
export USE_SELENIUM_FALLBACK=1
export DISABLE_AUTO_CHECK=0
export FLASK_DEBUG=1
```

Notes:
- `SECRET_KEY` is mandatory when `FLASK_DEBUG=0`.
- If `DATABASE_URL` is not set, SQLite file `tracker.db` is used.
- On Render production, set `FLASK_DEBUG=0`.

### 5) Run the app

Development:

```bash
python app.py
```

Production:

```bash
gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```

With `Procfile`, Render can run:

```text
web: gunicorn app:app
```

## Usage

### Web UI

- `/` shows landing page for logged-out users.
- `/dashboard` is the authenticated tracker dashboard.
- Register/login with username and password.
- Add a series using title + series listing URL.
- Use **Check All** to refresh latest chapters.
- Use **Continue** and unread badges to catch up quickly.
- Export/import backups from dashboard.

### Extension API

#### `POST /api/series/ensure`

Ensures a series exists.

```json
{
  "title": "Series Title",
  "url": "https://example.com/manga/series/",
  "series_key": "optional-stable-key"
}
```

#### `POST /api/progress`

Saves reading progress.

```json
{
  "series_url": "https://example.com/manga/series/",
  "series_key": "optional-stable-key",
  "chapter_url": "https://example.com/manga/series/chapter-42",
  "chapter_label": "Chapter 42",
  "chapter_num": 42.0
}
```

#### `POST /api/debug/scrape`

Debug scrape diagnostics for a given URL.

```json
{ "url": "https://asurascans.com/comics/some-series/" }
```

Returns candidate links, picked latest, parser version, confidence, and error flags.

## Configuration Reference

- `SECRET_KEY` – Flask session secret (required for production)
- `DATABASE_URL` – Postgres connection string
- `HTTP_TIMEOUT_SECONDS` – request timeout during scraping
- `MAX_CHECK_WORKERS` – concurrency for bulk checks
- `CHECK_INTERVAL_MINUTES` – scheduler interval
- `USE_SELENIUM_FALLBACK` – enable selenium fallback
- `DISABLE_AUTO_CHECK` – disable scheduler when set to `1`
- `PORT` – app port
- `FLASK_DEBUG` – debug mode toggle

## Troubleshooting

- **No chapters found**
  - Try `/api/debug/scrape` and inspect `error_flags`.
  - Use canonical series listing URL (not a chapter URL).
  - Enable Selenium fallback if site is heavily JS-rendered.

- **Selenium fails**
  - Install Chrome + ChromeDriver and ensure driver is available in PATH.

- **Slow checks**
  - Lower `MAX_CHECK_WORKERS` on small hosts.
  - Increase `CHECK_INTERVAL_MINUTES` for large bookmark sets.

- **Data reset on cloud**
  - Set `DATABASE_URL` and use PostgreSQL on Render.

## License

MIT
