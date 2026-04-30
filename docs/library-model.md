# Library data model

This app is moving from a **bookmark-centric** library to a **normalized series + sources** model. Bookmarks remain the compatibility layer for the dashboard, import/export, reading progress, and extensions until those areas are migrated.

## Legacy: `bookmarks`

Each row is one tracked listing URL for a user.

Typical fields:

- **Identity:** `id`, `user_id`
- **Listing:** `title`, `url`, `canonical_title`, `description`, `cover_url`, `chapter_count`
- **Progress / checks:** `latest_seen`, `latest_seen_num`, `latest_seen_url`, `last_checked`, `new_update`, read-chapter columns where migrated
- **Grouping:** `story_id`, `series_key`
- **Source metadata:** `source_name`, `source_domain`, `support_level`, `detection_source`
- **Timestamps / misc:** `created_at`, parser metadata columns

Uniqueness is enforced per user on normalized URL (`user_id`, `url`).

## Normalized: `series`, `series_source`, `user_library_item`

- **`series`** — one canonical title (slug, display title, normalized title key for dedupe, description, cover, type/status, timestamps).
- **`series_source`** — one source listing for that series (`source_url`, normalized URL for global dedupe, domain/name, support level, policy, detection source, latest chapter metadata, `health_status`, chapter count, timestamps). Does not store chapter/panel image blobs.
- **`user_library_item`** — ties a user to a `series` with a `preferred_source_id` and per-user settings (`status`, `notifications_enabled`).

## Dual-write transition

`POST /api/library/add-from-preview` (used by the app and the extension) **still inserts or dedupes a `bookmarks` row** as before, and **also** upserts normalized rows:

1. Resolve public HTTP(S) listing URL (existing SSRF-safe validation).
2. `Series` / `SeriesSource` (dedupe by normalized source URL globally; series by slug / normalized title key).
3. `UserLibraryItem` (dedupe by `user_id` + `series_id`; updates preferred source).

The JSON response includes a `library` object with normalized ids for clients that want them.

## Public source comparison

`GET /series/<slug>` prefers, in order:

1. MangaDex UUID builder (when the slug is a MangaDex id),
2. A normalized `series` row when `slug` matches the DB,
3. The local discovery catalog fallback.

NSFW sources registered in the source manifest are **omitted** from public comparison rows. Recommended source selection uses support level priority (`official_api` → `site_adapter` → `extension_assisted` → `generic_detector` → manual) and skips **blocked / broken / unavailable** health.

## Discover links

Discover and home cards set `comparison_slug` when a normalized series exists for the same catalog slug or normalized title, so **View sources** can open `/series/<normalized slug>` when available.
