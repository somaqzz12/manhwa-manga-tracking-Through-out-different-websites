# Blueprint Dependency Audit (Stage 0)

Purpose: map route-group dependencies before any Blueprint extraction, and prevent forbidden imports from `app.py`.

Rules for extraction:
- Blueprint modules must not import from `app.py`.
- Shared helpers must move first into dedicated modules (db/auth/services/etc.).
- Route groups move only after their shared dependencies are extracted.

## Proposed target modules

- `db.py`
- `auth/helpers.py`
- `services/security.py`
- `services/scraping.py`
- `services/bookmarks.py` (or `services/library.py`)
- `services/extension_progress.py`
- `services/admin.py`

## Route-group dependency map

### 1) Auth routes (`/auth`, `/login`, `/register`, `/logout`)

- **DB helpers used**
  - `get_conn()`
  - user CRUD/lookups in auth flow
- **Auth/session helpers used**
  - `login_required()`
  - `get_current_user()`
  - `_safe_internal_redirect_path()`
  - `_login_redirect_preserve_destination()`
- **Security helpers used**
  - password hashing/checking
  - CSRF integration (`CSRFProtect`)
- **Template/context helpers used**
  - `render_template("auth.html", ...)`

Must extract first:
- `db.py`
- `auth/helpers.py`
- `services/security.py` (token/redirect safety helpers if shared)

### 2) Library/dashboard routes (`/app`, `/add`, `/check*`, `/mark*`, `/bookmark/*`, import/export, duplicates)

- **DB helpers used**
  - `get_conn()`
  - DB query helpers in dashboard/list/edit/check flows
- **Auth/session helpers used**
  - `login_required()`
  - `get_current_user()`
  - `get_actor_user_id()`
- **Scraping helpers used**
  - `fetch_public_url()`
  - `scrape_bs4()`, `scrape_selenium()`, `scrape_latest_update()`
  - source scraping selection helpers
- **Bookmark/library helpers used**
  - `normalize_bookmark_url()`
  - `resolve_series_listing_url()`
  - `check_single()`, `check_all()`
  - progress helpers (`upsert_progress`, prune helpers)
  - story grouping/card aggregation helpers
- **Security/CSRF helpers used**
  - CSRF-exempt API routes under library
- **Template/context helpers used**
  - dashboard/public rendering helpers and flash redirects

Must extract first:
- `db.py`
- `services/scraping.py`
- `services/bookmarks.py` / `services/library.py`
- `auth/helpers.py`

### 3) Extension API routes (`/api/series/ensure`, `/api/progress`, `/api/unread-count`, `/api/reader-overlay`)

- **DB helpers used**
  - `get_conn()`
- **Auth/session helpers used**
  - `api_session_user_id()`
- **Bookmark/library helpers used**
  - `normalize_bookmark_url()`
  - `resolve_series_listing_url()`
  - ensure+progress lookup/update helpers
- **Security helpers used**
  - extension/session authorization
  - CSRF exemptions for extension JSON APIs
- **Source helpers used**
  - optional source profile lookups and metadata helpers

Must extract first:
- `db.py`
- `auth/helpers.py` (session helpers)
- `services/bookmarks.py`
- `services/extension_progress.py`
- `services/security.py` (extension-token/origin helpers)

### 4) Admin routes (`/admin/*`, debug scrape, maintenance merge)

- **DB helpers used**
  - `get_conn()`
  - admin-only query/report helpers
- **Auth/session helpers used**
  - `get_current_user()`
- **Security helpers used**
  - `admin_api_authorized()`
  - `admin_view_authorized()`
  - `_admin_secret_from_request()`
  - `_admin_link_kw()`
- **Scraping helpers used**
  - debug scrape endpoints call scraping helpers
- **Template/context helpers used**
  - admin templates and diagnostics rendering

Must extract first:
- `db.py`
- `services/security.py`
- `services/admin.py`
- `services/scraping.py` (for debug scrape)

### 5) Public/discovery routes (`/`, `/discover`, `/sources`, `/series/<slug>`, `/api/discover/*`, `/api/resolve-url`)

- **DB helpers used**
  - `get_conn()` for normalized/public series fallback
- **Auth/session helpers used**
  - `get_current_user()` for context
- **Source resolver helpers used**
  - `source_engine_normalize_url`
  - `source_engine_resolve_url`
  - metadata discovery + source registry helpers
- **Security helpers used**
  - safe URL/public-host checks
  - image-proxy safety checks
- **Template/context helpers used**
  - discover/public templates

Must extract first:
- `db.py`
- `services/security.py`
- `services/source_helpers.py` (optional consolidation)

## High-risk shared helpers currently in `app.py`

These must be moved before Blueprint extraction:
- DB layer: `get_conn()`, init/migration/runtime DB helpers.
- Auth/session: `login_required()`, `get_current_user()`, `api_session_user_id()`, redirect safety helpers.
- Security/admin: `admin_api_authorized()`, `admin_view_authorized()`, admin secret/token parsing.
- Scraping/fetch: `fetch_public_url()`, `scrape_*` helpers.
- Bookmark canonicalization: `normalize_bookmark_url()`, `resolve_series_listing_url()`.
- Extension flows: `ensure_series()`, `save_progress()`, unread/overlay related shared helpers.

## Extraction gating checklist

Before moving any route group:
- [ ] No route module needs `from app import ...`.
- [ ] All shared helper imports resolve from dedicated modules.
- [ ] `python -m compileall .` passes.
- [ ] `pytest` passes.
- [ ] App import-cycle test passes.

