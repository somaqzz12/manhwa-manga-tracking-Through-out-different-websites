# Source Registry Notes (Current + Direction)

## Current State

The project currently has multiple source-definition layers:

- `sources/sources.manifest.json` (large extension-derived manifest)
- `sources/catalog.json` (legacy catalog)
- `sources/registry.py` (policy/adapters list)
- hardcoded preview/demo source snippets in app/discovery paths

## Direction

Use one canonical source registry interface for the website:

1. Canonical data file(s): manifest/registry
2. Canonical loader/normalizer: `services/source_registry.py`
3. Website pages (`/sources`, discovery, recommendations) read from that interface
4. Templates never hardcode source websites or ranking rules

## Product Rule Integration

- Supported URL -> automatic handling
- Unsupported URL -> manual tracking fallback
- Requested URL/domain -> source request queue for future adapters

## Safety

The registry tracks metadata and compatibility status only.
No hosting of manga pages/images and no bypass behavior.

