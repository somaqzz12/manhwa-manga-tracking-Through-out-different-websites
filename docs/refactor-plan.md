# Refactor Plan (Small Safe Steps)

This plan is intentionally incremental and keeps pages working during migration.

## Constraints

- Website is the primary product surface.
- Extension is a companion detection tool.
- Source engine is separate from UI rendering.
- Templates display data only; business logic moves to services.
- Source registry is centralized.
- No destructive rewrites, no big-bang branch.

## Phase A - Preparation (Completed in this pass)

- Added:
  - `docs/product-plan.md`
  - `docs/source-policy.md`
  - `docs/route-map.md`
- Verified:
  - `.gitignore` and `.env.example` exist
- Safe CSS extraction started for simple pages:
  - `static/css/public-pages.css`

## Phase B - Route Module Split (No behavior changes)

Create route modules that import existing helper/service functions from `app.py` initially, then move internals gradually.

Proposed modules:

- `app/routes/public.py`
  - `/`, `/discover`, `/search`, `/series/<slug>`, `/about`
- `app/routes/dashboard.py`
  - `/app`, `/dashboard`, `/next`, `/app/add`, `/bookmark/*`, `/check*`, `/add`, `/delete`
- `app/routes/sources.py`
  - `/sources`, `/source-requests`, `/source-requests/<id>/vote`
- `app/routes/api.py`
  - `/api/*`

Execution pattern:

1. Introduce Blueprint files with thin wrappers.
2. Keep existing function bodies untouched at first (import + delegate).
3. Register blueprints in app factory/bootstrap.
4. Remove duplicate route decorators from monolith only after parity checks.

## Phase C - Service Boundary Cleanup

Move logic from routes/templates into explicit services:

- `services/discovery.py` (title search + discovery models)
- `services/resolver.py` (URL resolve orchestration)
- `services/recommendations.py` (source scoring/recommendation)
- `services/tracker.py` (add/update library workflows)
- `services/source_health.py` (health checks/status)

Rule: routes call services; templates only render passed data.

## Phase D - Source Engine Cleanup

Consolidate to one canonical source registry interface:

- Keep manifest/registry centralized (`services/source_registry.py` + `sources/*` adapters)
- Eliminate duplicate hardcoded source definitions in route files
- Keep policy tiers from one source of truth

## Phase E - CSS System Consolidation

Move remaining inline styles into centralized files:

- `static/css/theme.css`
- `static/css/layout.css`
- `static/css/components.css`

Then keep legacy `static/app.css` as compatibility layer until migration is complete.

## Phase F - Data Model Alignment (Planned)

Introduce/normalize data entities over time:

- `Series`
- `SeriesSource`
- `Chapter`
- `UserLibraryItem`
- `SourceRequest`
- `UpdateEvent`
- `SourceHealth`

## Safety Checklist Per Step

Each migration step must:

1. keep existing endpoints working
2. preserve auth/CSRF behavior
3. run regression tests
4. avoid schema-destructive DB changes without migration script
5. avoid extension-breaking API changes unless versioned/compatible

