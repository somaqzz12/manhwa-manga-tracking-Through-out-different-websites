# Manga Tracker

A self-hosted manga and manhwa tracker. Add a series listing URL, the server scrapes the latest chapter every 30 minutes, the dashboard shows what you're behind on, and an optional Chrome extension picks up the chapter you're currently reading and syncs progress automatically.

![Dashboard screenshot](docs/screenshot.png)

> Replace `docs/screenshot.png` with a real screenshot once you take one.

## Features

- Local accounts with hashed passwords, CSRF protection, and rate-limited auth.
- Add series from any reader by pasting the series listing URL.
- Automatic latest-chapter detection on a 30-minute schedule (configurable, runnable in parallel).
- Site profiles for popular hosts (AsuraScans, MangaKatana, ArenaScan, MangaDex, etc.) plus generic heuristics for everything else.
- Cover image extraction from Open Graph tags or the largest cover image on the page.
- Optional Selenium fallback for JS-only sites that block plain HTTP scraping.
- Reading progress tracked per chapter, "Continue" links that resume where you left off, and an unread badge per series.
- Mark-all-seen for the whole library, plus per-series mark-as-seen and read-through actions.
- Sortable, paginated, searchable dashboard with light/dark theme.
- Full JSON import/export for backup or migrating between hosts.
- Browser extension (Chromium): auto-detects chapter pages, optional silent auto-track, badge counter for unread chapters, right-click "Track this manga chapter", and an `Alt+Shift+T` shortcut.
- PostgreSQL in production, SQLite for local dev.
- Render-ready: the included [`render.yaml`](render.yaml) provisions a web service plus managed Postgres in one click.

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend framework | Flask 3, Flask-WTF, Flask-Limiter |
| Scheduler | APScheduler (background chapter checks) |
| Scraping | requests + BeautifulSoup4, optional Selenium + ChromeDriver fallback |
| Database | SQLite (local dev) or PostgreSQL via `psycopg[binary]` (production) |
| Frontend | Jinja templates + hand-written CSS, no JS framework |
| Server | gunicorn (production), Flask dev server (local) |
| Extension | Chrome MV3 service worker, vanilla JS, Shadow DOM modal |

## Quick start

```bash
pip install -r requirements.txt
export SECRET_KEY="dev-secret-change-me"
python app.py
```

Then open <http://127.0.0.1:5000>, register a user, and paste a series listing URL. On Windows PowerShell, replace `export` with `$env:SECRET_KEY = "..."`.

## Deploy on Render

The repo ships with a [`render.yaml`](render.yaml) blueprint that provisions:

- a free web service running `python app.py`,
- a free managed Postgres instance,
- environment defaults that lock down production (`FLASK_DEBUG=0`, `REQUIRE_API_AUTH=1`, `ALLOW_SQLITE_IN_PRODUCTION=0`),
- an auto-generated `SECRET_KEY`.

In Render, choose **New → Blueprint**, point it at this repository, and accept the defaults. The web service will refuse to start without a `DATABASE_URL` in production, so let the blueprint wire that up for you.

## Environment variables

All configuration is via environment variables. The `Required?` column is what the server actually enforces; defaults below match `app.py` exactly.

| Variable | Required? | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | Required when `FLASK_DEBUG=0` | `dev-secret-change-me` | Flask session signing key. Generate at least 32 random bytes for production. |
| `DATABASE_URL` | Required in production | _(unset)_ | PostgreSQL connection string. When unset, the app falls back to a local `tracker.db` SQLite file. |
| `ALLOW_SQLITE_IN_PRODUCTION` | Optional | `0` | Set to `1` to allow SQLite when `FLASK_DEBUG=0`. Strongly discouraged on Render. |
| `FLASK_DEBUG` | Optional | `1` | Enables the Flask debugger and relaxes session/CSRF flags. Must be `0` in production. |
| `PORT` | Optional | `5000` | Port the dev server binds to. Render injects this automatically. |
| `LOG_LEVEL` | Optional | `INFO` | Standard Python log level. |
| `REQUIRE_API_AUTH` | Optional | `0` | When `1`, every `/api/*` route requires an authenticated session cookie. The browser extension forwards your dashboard cookie. |
| `ADMIN_API_TOKEN` | Optional | _(unset)_ | Bearer token that gates `/api/debug/scrape` and `/api/maintenance/merge-duplicates`. Routes return 404 when unset. |
| `CORS_ALLOW_ORIGINS` | Optional | _(unset)_ | Comma-separated list of origins allowed to call the API. |
| `SESSION_COOKIE_SECURE` | Optional | `1` in prod, `0` in debug | Forces the session cookie to HTTPS-only. |
| `HTTP_TIMEOUT_SECONDS` | Optional | `15` | Per-request timeout for the chapter scraper. |
| `MAX_CHECK_WORKERS` | Optional | `6` | Concurrency for "Check All". Lower on small Render plans. |
| `CHECK_INTERVAL_MINUTES` | Optional | `30` | Background scheduler interval. |
| `DISABLE_AUTO_CHECK` | Optional | `0` | Set to `1` to disable the scheduler entirely. |
| `INITIAL_AUTO_CHECK` | Optional | `0` | Set to `1` to fire one check pass right after startup. |
| `USE_SELENIUM_FALLBACK` | Optional | `1` | Whether to retry failed scrapes with Selenium. |
| `MIN_PASSWORD_LENGTH` | Optional | `8` | Minimum password length on registration. |
| `BOOKMARKS_PAGE_SIZE` | Optional | `60` | Bookmarks per dashboard page. |
| `READ_PROGRESS_MAX_PER_BOOKMARK` | Optional | `400` | Cap on stored chapter-read events per series. |
| `READ_PROGRESS_MAX_PER_USER` | Optional | `20000` | Hard cap on total reading-progress rows per user. |
| `PROGRESS_PRUNE_INTERVAL_HOURS` | Optional | `6` | How often the scheduler prunes overflow progress rows. |
| `IMPORT_MAX_BYTES` | Optional | `5242880` | Max upload size for the JSON importer. |
| `IMPORT_MAX_ITEMS` | Optional | `20000` | Max bookmarks accepted per import. |
| `AUTH_RATE_LIMIT_PER_IP` | Optional | `10/minute;60/hour` | Flask-Limiter rule applied to login/register per IP. |
| `AUTH_RATE_LIMIT_PER_USER` | Optional | `8/minute;30/hour` | Flask-Limiter rule applied per username. |
| `RATELIMIT_STORAGE_URI` | Optional | `memory://` (debug), Redis recommended in prod | Storage backend for Flask-Limiter. |
| `BUG_REPORT_URL`, `CONTACT_EMAIL`, `GITHUB_URL` | Optional | Defaults baked into the templates | Strings used in the footer. |
| `DEFAULT_USER_EMAIL` | Optional | `local@tracker` | Email used for the auto-created default user when no users exist. |

## Browser extension

A Chromium MV3 companion lives in [`extension/`](extension/). It detects chapter pages, prompts you the first time you visit a series, and forwards reads to `/api/series/ensure` and `/api/progress`.

### Install (unpacked)

1. Build is not required — the extension is plain JS.
2. Visit `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select the [`extension/`](extension/) folder.
3. Click the puzzle piece in the toolbar, pin **Manga Tracker**, and open the popup.
4. Open the options page (right-click the toolbar icon → **Options**) and set the backend URL to your tracker (e.g. `https://your-app.onrender.com` or `http://127.0.0.1:5000`).
5. Sign in to the dashboard once in the same browser profile so the session cookie is available; the extension forwards it on every API call.

### What you get

- Three-state popup: not configured, no chapter detected, chapter detected.
- Live `/healthz` connection dot.
- "Track now" / "Already tracked — save this chapter" depending on whether the series is in your library.
- Badge counter showing unread chapters across the whole library, refreshed every 30 minutes via `chrome.alarms`.
- Right-click **Track this manga chapter** context menu and an `Alt+Shift+T` shortcut.
- Optional silent auto-track that skips the prompt entirely.
- A debug log of the last 25 events visible on the options page.

### Supported sites

The content script auto-detects chapter pages on hosts whose domain matches any of these substrings, plus a per-host extractor map for higher accuracy on the most-used readers:

`asura`, `reaper`, `flame`, `scan`, `toon`, `manga`, `manhwa`, `manhua`, `webtoon`, `bato`, `comick`, `mangadex`, `manganato`, `mangakakalot`, `mangapark`, `mangabuddy`, `mangaowl`, `mangahere`, `mangafox`, `mangafire`, `kissmanga`, `manga4life`, `mangasee`, `lhtranslation`, `cosmicscans`, `luminousscans`, `anigliscans`, `leviatanscans`, `drakescans`, `isekaiscan`, `rizzcomic`, `rawkuma`, `tcb`, `zinmanga`, `earlymanga`.

MangaDex skips the DOM entirely and uses the public `api.mangadex.org` REST endpoint via the extension service worker.

The full extension roadmap and design notes are in [`EXTENSION_PLAN.md`](EXTENSION_PLAN.md).

### Publish on the Chrome Web Store (free for end users)

Google charges a **one-time $5 USD** registration fee per developer account. After that, listing the extension is free; users install it from the store at no cost.

1. **Register** at the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole).
2. **Privacy policy URL** (required for broad host access): use the policy in this repo, for example  
   `https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/blob/main/docs/EXTENSION_PRIVACY_POLICY.md`  
   (or host the same text on a simple site / GitHub Pages if you prefer a dedicated domain).
3. **Build the upload zip** (only production files — no `generate_icons.py`):

   ```powershell
   cd extension
   powershell -ExecutionPolicy Bypass -File .\package-for-store.ps1
   ```

   The artifact is `extension/dist/manga-tracker-companion-v<version>.zip`. Upload that zip as a **new item** (or new version) in the dashboard.

4. **Store listing assets**: short description (≤132 characters), detailed description, **128×128** icon (you can reuse `extension/icons/icon-128.png`), and **screenshots** (1280×800 or 640×400 are common sizes). Show the popup on a chapter page, the options screen, and the connection states reviewers care about.
5. **Permission justifications**: explain `storage`, `tabs`, `activeTab`, `alarms`, `contextMenus`, and **why** `<all_urls>` is needed (many independent reader domains; network traffic only goes to the user’s configured backend plus optional MangaDex API metadata — mirror [`docs/EXTENSION_PRIVACY_POLICY.md`](docs/EXTENSION_PRIVACY_POLICY.md)).
6. **Review**: submissions are usually checked within a few days. Fix any rejection notes and re-upload a new zip after bumping `"version"` in [`extension/manifest.json`](extension/manifest.json).

The extension’s `homepage_url` in the manifest points at this GitHub repository so users can read the source and file issues.

## API endpoints

Routes the extension and external clients can rely on. All `/api/*` routes are CSRF-exempt and honor `REQUIRE_API_AUTH`; admin routes additionally require `ADMIN_API_TOKEN`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/healthz` | None | Liveness probe used by Render and the extension popup connection dot. |
| `POST` | `/api/series/ensure` | Session (when `REQUIRE_API_AUTH=1`) | Idempotently create or look up a bookmark by `series_key` or `url`. |
| `POST` | `/api/progress` | Session | Record reading progress for a chapter and bump `latest_seen_*` if the user is ahead of the scraper. |
| `GET` | `/api/unread-count` | Session | Returns total unread, behind-count, per-series unread, and the user's `tracked_keys`. Used by the extension badge. |
| `POST` | `/api/debug/scrape` | Admin token | Returns candidate links, chosen latest, parser version, confidence, and error flags for a given URL. |
| `POST` | `/api/maintenance/merge-duplicates` | Admin token | Coalesces bookmarks that point at the same canonical series URL. |

Example request bodies are in `app.py` near each route, and the extension's call sites in [`extension/background.js`](extension/background.js) are the canonical clients.

## Known limitations

- **Cover images are best-effort.** Covers are scraped from Open Graph metadata and the largest visible image on the listing page. Sites that lazy-load behind JavaScript or hotlink-block requests will show a placeholder until you point the parser at a different URL.
- **Selenium is opt-in but heavy.** When `USE_SELENIUM_FALLBACK=1` (the default), the server starts ChromeDriver to retry pages that defeat plain HTTP scraping. This adds significant memory pressure on small Render plans and requires Chrome + ChromeDriver installed in the environment. Free Render builds include them, but custom hosts may not.
- **SQLite is for local dev only.** The bundled `tracker.db` is fine on your laptop, but on any cloud host the disk is ephemeral and you will lose data on every redeploy. Production refuses to boot without `DATABASE_URL` unless `ALLOW_SQLITE_IN_PRODUCTION=1`.
- **Heuristic chapter detection.** The extension and the scraper both fall back to URL/title heuristics for hosts without a per-site profile. Expect occasional misses on unusual readers; the per-host extractor map in [`extension/content.js`](extension/content.js) is the right place to add fixes.
- **Single-tenant by design.** Accounts are local to the instance you host. There is no SSO, no team sharing, and no cross-server sync.
- **MV3 service-worker lifecycle.** The extension background worker can be unloaded after ~30s idle. Long-running state lives in `chrome.storage` or is reconstructed from `chrome.alarms`/event listeners; if you fork the extension, do not assume module-scope variables persist.

## Issues and contributions

Bug reports and feature requests live on the GitHub issues page: <https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues>.

## License

MIT.
