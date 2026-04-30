# Source Manifest Policy

This repository commits only a **filtered safe manifest** at:

- `sources/sources.manifest.json`

The committed manifest is generated from a raw upstream file and is intentionally restricted for public repository safety.

## What is filtered out

The build step removes:

- Any extension with `nsfw: true`
- Any source with `nsfw: true`
- Any source with missing/empty `baseUrl`
- Any non-HTTP(S) URL (for example `file://`)
- Any local/private development host (`localhost`, `127.0.0.1`, `0.0.0.0`)

## Kept fields

Only these fields are preserved in the filtered manifest:

- Extension: `extension`, `package`, `language`, `version`, `nsfw`, `sources`
- Source: `name`, `lang`, `id`, `baseUrl`

`nsfw` is forced to `false` for committed extension entries.

## Raw upstream manifests are local-only

Raw/full manifests should not be committed. Common local filenames are ignored by `.gitignore`:

- `sources/sources.manifest.full.json`
- `sources/raw_manifest.json`
- `sources/upstream_manifest.json`
- `sources/*raw*.json`

## Build command

Use:

`python scripts/build_safe_sources_manifest.py --input <raw-upstream-manifest.json> --output sources/sources.manifest.json`

## Runtime policy

Runtime NSFW filtering remains in place as defense-in-depth, but repository policy requires the committed manifest itself to be safe.
