# Manga Watchlist

Live at **[mangawatchlist.space](https://mangawatchlist.space)**.

> **Note:** repository directory name is still `manga-tracker` for historical reasons. The product brand is **Manga Watchlist**.

> **License:** This project is licensed under [PolyForm Noncommercial 1.0.0](LICENSE). Commercial use is not permitted without explicit permission.

A self-hosted manga and manhwa tracker. Add a series listing URL, the server scrapes the latest chapter every 30 minutes, the dashboard shows what you're behind on, and an optional Chrome extension picks up the chapter you're currently reading and syncs progress automatically.

### What this system does (end-to-end)

1. **You run one web app** (Flask + gunicorn in production). It stores users, passwords (hashed), and each user’s **bookmarks**: a series title, the **series listing URL** you pasted, optional **series key** / **story grouping**, and **reading progress** (which chapter you last opened or marked seen).
2. **The server discovers “what’s latest”** by HTTP-fetching each bookmark’s listing page on a schedule (APScheduler). It uses a **JSON source catalog** ([`sources/catalog.json`](sources/catalog.json)) for known sites (selectors, MangaDex API, etc.) and **generic heuristics** for unknown hosts. Results are cached on each bookmark (latest chapter number, label, last check time). Optional **Selenium** can retry stubborn JS-heavy pages when enabled.
3. **The dashboard** is server-rendered HTML: library list, sort/search/pagination, “behind” / unread-style signals, **Continue** links, per-series and bulk **mark seen**, **check now**, **edit** (including linking **alternate URLs** for the same story), **import/export** JSON, **public list** slug, **RSS** with a secret token, optional **email** new-chapter notifications (SMTP), **source requests** voting, and static pages (**privacy**, **changelog**, **supported sources** with live **health** stats when `_health.json` exists).
4. **JSON and cookie-authenticated APIs** let the **Chrome extension** (same browser profile as your login) call **`/api/series/ensure`**, **`/api/progress`**, and **`/api/unread-count`** so chapter pages update your library without manually pasting URLs every time. A separate **Bearer API token** can drive **`/api/v1/bookmarks`** for scripts or integrations.
5. **Admin and maintenance** routes exist for power users (debug scrape, merge duplicates, user admin HTML) behind **`ADMIN_API_TOKEN`** / **`ADMIN_USERNAME`** as documented below.

This repository also contains an optional **Next.js** [`landing/`](landing/) site for marketing pages; the main product UI for logged-in use is the Flask app.

Dashboard screenshots live in repo docs once added: save a capture as `docs/screenshot.png` and uncomment the image line below if you want it in the GitHub-rendered README.

<!-- ![Dashboard screenshot](docs/screenshot.png) -->

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

- a free web service running **gunicorn** (`render.yaml` `startCommand`) — not Flask’s dev server,
- a free managed Postgres instance,
- environment defaults that lock down production (`FLASK_DEBUG=0`, `ALLOW_SQLITE_IN_PRODUCTION=0`),
  `CORS_ALLOW_ORIGINS` for the app host, and an optional `CHROME_EXTENSION_ID` so the extension
  origin is allowlisted without duplicating `chrome-extension://...` in env,
- an auto-generated `SECRET_KEY`.

In Render, choose **New → Blueprint**, point it at this repository, and accept the defaults. The web service will refuse to start without a `DATABASE_URL` in production, so let the blueprint wire that up for you.

After the first deploy, open Render → your web service → **Environment** and set **`CHROME_EXTENSION_ID`** to the 32-character id from `chrome://extensions` (developer mode → Details) for the **published** build. That value is merged into the CORS allowlist so the extension can send credentialed API requests. If you skip this until after store approval, the dashboard will work but the extension may get CORS errors until the id is set.

**Idle / keep-warm:** `GET /healthz` does not touch the database or run scrapers—it only returns JSON. Use UptimeRobot, Better Stack, cron-job.org, or similar to request `https://<your-app-host>/healthz` on a short interval (for example every 5 minutes) if your host would otherwise sleep after inactivity.

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
| `CHROME_EXTENSION_ID` | Optional | _(unset)_ | Published extension id; if set, `chrome-extension://<id>` is appended to the CORS allowlist. |
| `ADMIN_API_TOKEN` | Optional | _(unset)_ | Secret for `/api/debug/scrape`, `/api/maintenance/merge-duplicates`, and optional header-only access to `/admin/*`. Send as **`Authorization: Bearer <token>`** or **`X-Admin-Token`**. Routes return **404** when unset. **Query-string tokens are not accepted** (they leak via browser history and `Referer`). |
| `ADMIN_USERNAME` | Optional | _(unset)_ | If set, that **username** may open `/admin/users` after a normal dashboard login (recommended for the HTML admin UI in production). |
| `CORS_ALLOW_ORIGINS` | **Strongly required in production** | _(unset)_ | Comma-separated **exact** origins allowed to receive `Access-Control-Allow-Origin` with credentials. Must include your dashboard origin (e.g. `https://app.example.com`) and, unless you rely on `CHROME_EXTENSION_ID`, the full `chrome-extension://<id>` origin. With `FLASK_DEBUG=1` and an empty list, dev mode allows unpacked extensions and localhost only — not production-safe. |
| `SESSION_COOKIE_SECURE` | Optional | `1` in prod, `0` in debug | Forces the session cookie to HTTPS-only. |
| `HTTP_TIMEOUT_SECONDS` | Optional | `15` | Per-request timeout for the chapter scraper. |
| `MAX_CHECK_WORKERS` | Optional | `6` | Concurrency for "Check All". Lower on small Render plans. |
| `CHECK_INTERVAL_MINUTES` | Optional | `30` | Background scheduler interval. |
| `DISABLE_AUTO_CHECK` | Optional | `0` | Set to `1` to disable the scheduler entirely. |
| `INITIAL_AUTO_CHECK` | Optional | `0` | Set to `1` to fire one check pass right after startup. |
| `USE_SELENIUM_FALLBACK` | Optional | `0` | Whether to retry failed scrapes with Selenium. Keep disabled on small hosts. |
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
| `EXTENSION_ZIP_DOWNLOAD_URL` | Optional | _(built from `GITHUB_URL`)_ | Direct link for “Download extension (ZIP)” on the Flask dashboard/landing. Defaults to a one-click ZIP of `extension/` via [download-directory.github.io](https://download-directory.github.io/). Set this to a GitHub Release asset URL if you prefer. |
| `DEFAULT_USER_EMAIL` | Optional | `local@tracker` | Email for the auto-created **system** user used to attach legacy rows with `user_id` NULL. A **random** password hash is stored (not login-capable). Older DBs created before this change are rotated off the historical `local-only` password on startup. |
| `SOURCE_HEALTH_INTERVAL_HOURS` | Optional | `24` | How often the background job re-probes every `sample_series_url` in the catalog and writes `sources/_health.json` (gitignored; created per deploy). Set to `0` to disable. Also run `python scripts/check_sources.py` manually after catalog edits. |
| `PUBLIC_BASE_URL` | Optional | _(unset)_ | Canonical public site URL used for RSS `<link>` when the app sits behind a reverse proxy; if unset, each request falls back to `request.url_root`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional | _(unset)_ | When `SMTP_HOST` is set and a user opts in (`notify_email_chapters` on the account settings page), new-chapter notifications are sent via SMTP (port `465` SSL or `587` STARTTLS). |
| `DEAD_SERIES_WARNING_DAYS` | Optional | `120` | Dashboard flag when aggregating stale “last checked” ages (not a hard drop from the library). |

## Source catalog and health checks

- The committed `sources/sources.manifest.json` is filtered to non-NSFW public sources. Raw upstream manifests are local-only and ignored by Git.
- **Validate structure:** `python scripts/validate_catalog.py` — fails if any source is missing `sample_series_url` or domains (use in CI).
- **Probe all samples:** `python scripts/check_sources.py` — writes `sources/_health.json` (gitignored; generate on each server or in release automation) used by `/sources` and `GET /api/registry/public`.
- **Scheduler:** When `SOURCE_HEALTH_INTERVAL_HOURS` is greater than `0`, the same probe runs on that interval in-process (single leader; see `SCHEDULER_LEADER`).

## Docker Compose (sketch)

The repo ships [`docker-compose.yml`](docker-compose.yml) with Postgres and the Flask app on port **8000**. Set a strong **`SECRET_KEY`** in your environment before `docker compose up --build` (the compose file does not inject a dev default; `FLASK_DEBUG` is `0`). Tune further for production (CORS, `DATABASE_URL`, scheduler flags, TLS in front).

## Browser extension

A Chromium MV3 companion lives in [`extension/`](extension/). It detects chapter pages, prompts you the first time you visit a series, and forwards reads to `/api/series/ensure` and `/api/progress`.

**Install, self-hosting, and zip packaging:** see [`extension/README.md`](extension/README.md). **What the extension does *not* contain** (secrets, other users’ data): see [`extension/SECURITY.md`](extension/SECURITY.md).

### Install (unpacked)

1. Build is not required — the extension is plain JS.
2. Visit `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select the [`extension/`](extension/) folder.
3. Click the puzzle piece in the toolbar, pin **Manga Watchlist**, and open the popup.
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

   **Easiest on Windows:** open File Explorer, go to the [`extension/`](extension/) folder, and **double-click** [`package-for-store.cmd`](extension/package-for-store.cmd). A console window opens; when it says “Done”, your zip is in `extension/dist/`.

   **Or from a terminal** (must be **inside** `extension/`, not the repo root):

   ```powershell
   cd c:\Users\YOUR_NAME\manga-tracker\extension
   powershell -NoProfile -ExecutionPolicy Bypass -File .\package-for-store.ps1
   ```

   If you run the script from the wrong folder you get *manifest.json not found*. If Windows blocks scripts, the `.cmd` file bypasses that.

   The artifact is `extension/dist/manga-watchlist-companion-v<version>.zip`. Upload that zip as a **new item** (or new version) in the dashboard.

4. **Store listing assets**: short description (≤132 characters), detailed description, **128×128** icon (you can reuse `extension/icons/icon-128.png`), and **screenshots** (1280×800 or 640×400 are common sizes). Show the popup on a chapter page, the options screen, and the connection states reviewers care about.
5. **Permission justifications**: explain `storage`, `tabs`, `activeTab`, `alarms`, `contextMenus`, and **why** `<all_urls>` is needed (many independent reader domains; network traffic only goes to the user’s configured backend plus optional MangaDex API metadata — mirror [`docs/EXTENSION_PRIVACY_POLICY.md`](docs/EXTENSION_PRIVACY_POLICY.md)).
6. **Review**: submissions are usually checked within a few days. Fix any rejection notes and re-upload a new zip after bumping `"version"` in [`extension/manifest.json`](extension/manifest.json).

The extension’s `homepage_url` in the manifest points at this GitHub repository so users can read the source and file issues.

## API endpoints

Routes the extension and external clients can rely on. User JSON routes (`/api/series/ensure`, `/api/progress`, `/api/unread-count`) are CSRF-exempt and **always require a signed-in dashboard session** (no anonymous default user). Configure production CORS with `CORS_ALLOW_ORIGINS` / `CHROME_EXTENSION_ID` so the extension can send cookies. Admin **JSON** routes (`/api/debug/scrape`, `/api/maintenance/merge-duplicates`) require **`FLASK_DEBUG=1`**, or the **`ADMIN_API_TOKEN`** via **`Authorization: Bearer`** / **`X-Admin-Token`**, or a signed-in user whose **username** matches **`ADMIN_USERNAME`** (not any logged-in user). Admin **HTML** pages (`/admin/*`) require signing in as `ADMIN_USERNAME` or the same headers (e.g. via a reverse proxy).

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/healthz` | None | Liveness probe used by Render and the extension popup connection dot. |
| `POST` | `/api/series/ensure` | Session (required) | Idempotently create or look up a bookmark by `series_key` or `url`. |
| `POST` | `/api/progress` | Session | Record reading progress for a chapter and bump `latest_seen_*` if the user is ahead of the scraper. |
| `GET` | `/api/unread-count` | Session | Returns total unread, behind-count, per-series unread, and the user's `tracked_keys`. Used by the extension badge. |
| `GET` | `/api/registry/public` | None | Registry snapshot for clients (short `Cache-Control`). |
| `GET` | `/feeds/rss/<token>` | Per-user RSS secret | Private RSS feed (`PUBLIC_BASE_URL` helps behind reverse proxies). Manage from `/account/settings`. |
| `GET` | `/api/library/duplicate-hints` | Session | Duplicate-title hint groups (merge candidates). |
| `POST` | `/api/library/merge-bookmarks` | Session JSON | `{keeper_id, merge_ids}` — unify `story_id`s like the Edit flow. |
| `GET` | `/api/library/chapter-map` | Session | Per-`story_id` source rows (multi-site diagnostics). |
| `GET` | `/api/library/alt-sources` | Session (`?url=`) | Suggests other catalog entries that appear healthy (`_health.json`). |
| `GET` | `/api/v1/bookmarks` | Bearer API token (`/account/settings`) | Aggregate bookmarks JSON (`POST /api/account/api-token` rotates the token while logged in). |
| `POST` | `/api/import/mal` | Session JSON | **`501`** — stub for future imports. |
| `POST` | `/api/debug/scrape` | Session **or** Bearer / `X-Admin-Token` | Returns candidate links, chosen latest, parser version, confidence, and error flags for a given URL. |
| `POST` | `/api/maintenance/merge-duplicates` | Session **or** Bearer / `X-Admin-Token` | Coalesces bookmarks that point at the same canonical series URL. |

Example request bodies are in `app.py` near each route, and the extension's call sites in [`extension/background.js`](extension/background.js) are the canonical clients.

## Known limitations

- **Local verification needs dependencies.** `python -m unittest` and running Flask require packages from `requirements.txt` (e.g. Flask, BeautifulSoup). Sandboxed or offline shells may block `pip install`. **Windows:** `npm run build` can fail with `spawn EPERM` if policy or antivirus blocks child processes; try another directory, an exemption, or WSL.
- **Cover images are best-effort.** Covers are scraped from Open Graph metadata and the largest visible image on the listing page. Sites that lazy-load behind JavaScript or hotlink-block requests will show a placeholder until you point the parser at a different URL.
- **Selenium is opt-in and heavy.** When `USE_SELENIUM_FALLBACK=1`, the server starts ChromeDriver to retry pages that defeat plain HTTP scraping. This adds significant memory pressure on small Render plans and requires Chrome + ChromeDriver installed in the environment. Keep it disabled unless you are on a host with enough memory.
- **SQLite is for local dev only.** The bundled `tracker.db` is fine on your laptop, but on any cloud host the disk is ephemeral and you will lose data on every redeploy. Production refuses to boot without `DATABASE_URL` unless `ALLOW_SQLITE_IN_PRODUCTION=1`.
- **Heuristic chapter detection.** The extension and the scraper both fall back to URL/title heuristics for hosts without a per-site profile. Expect occasional misses on unusual readers; the per-host extractor map in [`extension/content.js`](extension/content.js) is the right place to add fixes.
- **Single-tenant by design.** Accounts are local to the instance you host. There is no SSO, no team sharing, and no cross-server sync.
- **MV3 service-worker lifecycle.** The extension background worker can be unloaded after ~30s idle. Long-running state lives in `chrome.storage` or is reconstructed from `chrome.alarms`/event listeners; if you fork the extension, do not assume module-scope variables persist.

## Issues and contributions

Bug reports and feature requests live on the GitHub issues page: <https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues>.

Continuous integration (`.github/workflows/ci.yml`) validates the source catalog, runs `python -m unittest`, and builds the `landing/` Next.js site on every push / pull request.

## License

Copyright (c) Alex Rowan. **Manga Watchlist** (code, docs, and extension in this repository) is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE) (SPDX: `PolyForm-Noncommercial-1.0.0`).

In plain language: you may **use, study, change, and share** this project for **noncommercial** purposes (personal use, learning, hobby projects, and similar). Uses that are primarily **commercial**—for example selling access, running a paid competing hosted service based on this codebase, or redistributing as part of a paid product—are **not** covered by that license; you need **separate written permission** from the copyright holder.

The **Manga Watchlist** name and branding are not a grant to use the same product name or logo for someone else’s product. Forks should keep the license and notices intact (see the `Required Notice` line in [LICENSE](LICENSE)).

This is not legal advice. For commercial licensing questions, open a GitHub issue or use the contact route you publish in the app footer.
