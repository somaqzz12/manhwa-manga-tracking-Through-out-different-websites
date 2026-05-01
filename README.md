# Manga Watchlist

Self-hosted manga, manhwa, manhua, and webtoon watchlist for tracking source URLs and reading progress across different websites.

Live at **[mangawatchlist.space](https://mangawatchlist.space)**.

> The repository folder is still named `manga-tracker` for historical reasons.

> Licensed under [PolyForm Noncommercial 1.0.0](LICENSE). Commercial use requires separate permission.

## What it does

- Save manga/manhwa/webtoon source URLs
- Track reading progress in one dashboard
- Check supported sources for latest chapter metadata
- Open the original source website
- Mark chapters as seen
- Import/export watchlist data
- Optional browser extension for assisted tracking ([`extension/README.md`](extension/README.md), [`extension/SECURITY.md`](extension/SECURITY.md))

## What it is not

Manga Watchlist is not a manga reader, mirror, downloader, or hosting platform.  
It does not host manga pages or chapters.

## Current status

This project is early but working. Some sources are automatic, while unsupported sources can still be saved manually.

**Optional demo-style UI:** set `SHOW_DEMO_CONTENT=1` for broader discover/marketing routes; default keeps the app tracker-focused.

## How source support works

- **Supported source:** automatic metadata/checking (where the [catalog](sources/catalog.json) allows it)
- **Unsupported safe source:** manual tracking / requested support
- **Blocked source:** unsafe, protected, login-only, dead, or unsuitable

Validate catalog structure: `python scripts/validate_catalog.py`. Probe samples: `python scripts/check_sources.py` (writes gitignored `sources/_health.json`).

## Quick start

**Python (local dev)**

```bash
pip install -r requirements.txt
export SECRET_KEY="dev-secret-change-me"
python app.py
```

Open <http://127.0.0.1:5000>, register, and add a series. On Windows PowerShell: `$env:SECRET_KEY = "dev-secret-change-me"`.

**Docker (Postgres + app on port 8000)**

```bash
cp .env.example .env
# Set SECRET_KEY in .env (or export it in your shell). Compose substitutes ${SECRET_KEY} for the web service.
docker compose up --build
```

Then open <http://127.0.0.1:8000>. See [`docker-compose.yml`](docker-compose.yml) for defaults.

## Tech stack (brief)

Flask, Jinja templates and static CSS, SQLite for local dev or PostgreSQL in production, background jobs via APScheduler, and a Chrome MV3 extension (vanilla JS). An optional Next.js marketing site lives in [`landing/`](landing/).

## Tests

Same as CI:

```bash
python scripts/validate_catalog.py
python -m unittest discover
```

The [`landing/`](landing/) app is also linted and built in CI (`npm run lint`, `npm run build`).

## Deploy (Render)

Use **New → Blueprint** with [`render.yaml`](render.yaml). After deploy, set **`CHROME_EXTENSION_ID`** for extension CORS. Ping **`GET /healthz`** if your host idles to sleep.

## Configuration

Full list: **[`.env.example`](.env.example)**. Common production variables: `SECRET_KEY`, `DATABASE_URL`, `CORS_ALLOW_ORIGINS`, `CHROME_EXTENSION_ID`, `SHOW_DEMO_CONTENT`, optional `ADMIN_API_TOKEN` / `ADMIN_USERNAME`.

## Extension

Install unpacked from [`extension/`](extension/); set backend URL in options; sign in to the dashboard in the same browser profile. Roadmap: [`docs/extension-plan.md`](docs/extension-plan.md). Store privacy copy: [`docs/EXTENSION_PRIVACY_POLICY.md`](docs/EXTENSION_PRIVACY_POLICY.md).

## API (summary)

Extension session routes: `POST /api/series/ensure`, `POST /api/progress`, `GET /api/unread-count`. **`GET /healthz`** needs no auth. Details in [`app.py`](app.py) and [`extension/background.js`](extension/background.js).

## Contributing / CI

Issues: <https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues>.  
Public roadmap (when deployed): `/roadmap` on your instance (e.g. <https://mangawatchlist.space/roadmap>).  
CI: catalog validation, `python -m unittest discover`, `landing/` lint/build.

## License

Copyright (c) Alex Rowan. Use under [PolyForm Noncommercial 1.0.0](LICENSE). Forks should retain license and notice text. Not legal advice.
