# Route Map (Current State)

This is the extracted route inventory from `app.py` before modularization.

## Public Website Pages

- `GET /` -> landing
- `GET /discover` -> discovery page (title search + URL resolve UX)
- `GET /search` -> currently redirects to `/discover`
- `GET /series/<slug>` -> public series/source comparison page
- `GET /about` -> about page
- `GET /sources` -> supported sources page
- `GET /source-requests` -> source requests page
- `POST /source-requests` -> create request
- `POST /source-requests/<int:req_id>/vote` -> vote request
- `GET /privacy` -> privacy page
- `GET /changelog` -> changelog page
- `GET /demo` -> demo dashboard
- `GET /healthz` -> health check

## Auth / Account

- `GET|POST /auth` -> sign in/register
- `POST /logout` -> logout
- `GET|POST /account/settings` -> account settings
- `GET|POST /account/delete` -> delete account
- `GET /feeds/rss/<token>` -> private RSS feed
- `GET /list/<slug>` -> public list page

## Dashboard Website Pages

- `GET /app` and `GET /dashboard` -> main dashboard
- `GET /app/library` -> dashboard alias redirect
- `GET /app/add` -> add URL page
- `GET /app/search` -> dashboard search redirect
- `GET /app/series/<int:series_id>` -> app series detail
- `GET /app/requests` -> requests alias redirect
- `GET /app/settings` -> settings alias redirect
- `GET /next` -> next-up page

## Dashboard Actions (HTML Form POST)

- `GET /export` -> export JSON backup
- `POST /import` -> import JSON backup
- `POST /add` -> add bookmark
- `POST /check/<int:bookmark_id>` -> check one bookmark
- `POST /check-story` -> check story group
- `POST /check-all` -> check all bookmarks
- `POST /mark-seen/<int:bookmark_id>` -> mark one seen
- `POST /mark-all-seen` -> mark all seen
- `POST /bookmark/<int:bookmark_id>/read-through` -> read-through action
- `GET|POST /bookmark/<int:bookmark_id>/edit` -> edit bookmark
- `POST /delete/<int:bookmark_id>` -> delete bookmark
- `POST /onboarding/dismiss` -> dismiss onboarding banner

## API Routes

- `POST /api/import/mal`
- `GET /api/registry/public`
- `GET /api/check-all/status`
- `POST /api/series/ensure`
- `POST /api/progress`
- `GET /api/unread-count`
- `GET /api/library/duplicate-hints`
- `POST /api/library/merge-bookmarks`
- `GET /api/library/chapter-map`
- `GET /api/library/alt-sources`
- `POST /api/resolve-url`
- `POST /api/track`
- `GET /api/search`
- `GET /api/series/<int:series_id>/sources`
- `POST /api/source-request`
- `GET /api/trending`
- `GET /api/recent-updates`
- `GET /api/discover/supported-sources`
- `GET /api/discover/search`
- `GET /api/discover/series/<int:series_id>`
- `GET /api/discover/series/<int:series_id>/sources`
- `POST /api/discover/search-live`
- `POST /api/tracker/add-series`
- `GET /api/v1/bookmarks`
- `POST /api/account/api-token`
- `GET /api/reader-overlay`
- `POST /api/debug/scrape`
- `POST /api/maintenance/merge-duplicates`

## Admin

- `GET /admin/users`
- `GET /admin/users/<int:user_id>`

---

## Target Consolidated Public/App Shape (Direction)

This route surface will be preserved while internal code is split:

- `/` landing
- `/discover` public search + URL discovery
- `/series/<slug>` public source comparison
- `/app` dashboard
- `/app/add` add URL
- `/app/sources` source hub (or alias to `/sources`)
- `/app/settings` settings

