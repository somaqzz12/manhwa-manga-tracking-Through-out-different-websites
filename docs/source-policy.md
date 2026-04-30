# Source Policy

## Scope

Manga Watchlist is a metadata and tracking product.

- Allowed:
  - Store series metadata and source URLs
  - Parse chapter identifiers and update status
  - Maintain source health snapshots and adapter status
  - Offer manual fallback when automatic detection is unavailable
- Not allowed:
  - Host manga pages or image assets
  - Bypass paywalls, DRM, Cloudflare, anti-bot protections, or signed/private APIs
  - Store private third-party access tokens scraped from user traffic

## Operational Rules

1. Centralize source definitions in one registry/manifest.
2. Keep source ranking and recommendation logic in services, not templates.
3. Keep website UX decoupled from extension behavior.
4. Treat unsupported URLs as manual-trackable, not hard failures.
5. Use source requests to prioritize future adapters.

## Safety Rule

Do not host manga pages or images.
Do not bypass paywalls, Cloudflare, private tokens, signed APIs, DRM, or anti-bot protections.
Track metadata, source URLs, chapter numbers, and update status only.
