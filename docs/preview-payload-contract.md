# Preview Payload Contract

Canonical preview shape used by:

- `/api/resolve-url`
- extension `RESOLVE_URL` result path
- `/api/library/add-from-preview`

```json
{
  "source_url": "https://example.com/series/demo",
  "source_name": "Example Source",
  "source_domain": "example.com",
  "support_level": "official_api | site_adapter | generic_detector | extension_assisted | manual_only",
  "title": "Display title",
  "canonical_title": "Canonical title",
  "description": "Optional summary",
  "cover_url": "https://cdn.example.com/cover.jpg",
  "latest_chapter": "123",
  "current_chapter": "122",
  "chapter_count": 200,
  "chapters": [
    { "url": "https://example.com/series/demo/ch-123", "number": "123", "title": "Optional chapter title" }
  ],
  "warnings": ["Optional warning"],
  "detection_source": "backend | extension | manual",
  "confidence": 0.0
}
```

Notes:

- `source_url` must be public `http(s)` only.
- `cover_url` is optional and must be public `http(s)` when present.
- `chapters` are metadata links only (never page/panel data ingestion).
