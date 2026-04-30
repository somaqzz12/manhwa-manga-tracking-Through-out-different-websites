# Source Resolution Contract

Given a URL, the resolver must:

1. Normalize input URL.
2. Extract domain.
3. Check curated catalog entries in `sources/catalog.json` first.
4. Check generated manifest entries in `sources/sources.manifest.json` second.
5. Pick adapter/resolution strategy from the resolved source profile.
6. If no adapter/profile matches, use generic detection.
7. If detection fails, return `manual_only` (never crash user flow).
8. Never allow generated manifest entries to downgrade curated adapters.

## Deterministic Precedence Rules

- Curated catalog is the source-of-truth for known domains.
- Manifest is supplemental discovery data only.
- If domains overlap, curated always wins.
- Health status decorates availability only; it does not replace parsing strategy or adapter type.

## Product Rule Mapping

- Supported URL -> automatic flow.
- Unsupported URL -> manual tracking flow.
- Requested URL/domain -> request queue for future adapter work.

## Safety Constraints

- No hosting manga pages/images.
- No bypass of paywalls, Cloudflare, private tokens, signed APIs, DRM, or anti-bot protections.
- Metadata and tracking only.
