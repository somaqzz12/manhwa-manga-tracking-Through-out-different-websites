# Product Plan

This project is a universal manga/manhwa discovery and tracking platform.

Users can search a title or paste any URL.
The app finds metadata, cover, chapters, available source websites, recommends the best source, and lets users add it to a tracker.

The browser extension is a companion detection tool, not the main product.

We do not host manga pages or images.
We store metadata, source URLs, chapter numbers, and update status.

## Core Product Direction

- Website-first experience:
  - `landing` for positioning and entry
  - `discover` for title lookup + URL resolution
  - `series detail` for source comparison and recommendation
  - `dashboard` for personal tracking and updates
- Extension as optional helper:
  - Detects reading context
  - Sends progress to the website APIs
  - Does not replace discovery, comparison, or tracking UX

## Product Rule

Any URL should be accepted.
Supported URLs become automatic.
Unsupported URLs become manual.
Requested URLs become future adapters.
