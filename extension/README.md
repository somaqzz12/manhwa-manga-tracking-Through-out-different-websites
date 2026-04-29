# Manga Watchlist — browser extension

This folder is the full **Chrome / Edge (Chromium) MV3** extension. There is no build step: load it as-is or zip it for the store.

## Quick install (use the hosted app)

**Fastest:** download **only this folder** as a ZIP (GitHub serves it via [download-directory](https://download-directory.github.io/)) — use the same link as on [mangawatchlist.space](https://mangawatchlist.space) (“Download extension (ZIP)”), or open your repo’s `main` branch tree at `extension/` and use the green **Code** button if you prefer.

1. Or clone / download the full repository (you only need the `extension/` folder).
2. Open `chrome://extensions` (or `edge://extensions`).
3. Turn on **Developer mode**.
4. Click **Load unpacked** and choose this **`extension`** directory (the one that contains `manifest.json`).
5. Open the extension **Options** and confirm the **API base URL** (default: official Manga Watchlist API). Use your own URL only if you self-host the Flask app.
6. In the **same browser profile**, open your dashboard, **register / sign in**. The extension sends your existing session cookie with API calls—no separate extension password.

### Download without Git

On GitHub: **Code → Download ZIP**, unzip, then load the `extension` subfolder as above.

### Package a zip (sharing or store upload)

From the repo root, see the main [README](../README.md) section **Publish on the Chrome Web Store** for `package-for-store.ps1` / `package-for-store.cmd`. The zip contains only extension assets, not the server or database.

## Self-hosted / local only

1. Run the Flask app locally (e.g. `http://127.0.0.1:5000`) or deploy your own instance.
2. In **Options**, set **API base URL** to that origin (no trailing slash).
3. Chrome may prompt for **additional host permission** for your origin—approve it for that install only.

That configuration affects **only that browser**. It does not give other people access to your deployment; they would still need accounts on **your** server if they pointed their extension at your URL.

## What this folder contains

| Contents | Purpose |
| --- | --- |
| `manifest.json` | Permissions, content scripts, service worker |
| `background.js` | API calls, alarms, context menu |
| `content.js` | Chapter detection on reader sites |
| `popup.html` / `popup.js` | Toolbar popup |
| `options.html` / `options.js` | Settings (API URL, auto-track, etc.) |
| `config.js` | Default public API base (change when forking for another product) |
| `icons/` | Toolbar / store icons |

There are **no** database connection strings, admin tokens, or user passwords in this folder. See [SECURITY.md](./SECURITY.md) for a short privacy and threat overview.

## Permissions (why they exist)

- **`storage`**: Save your API URL and preferences.
- **`tabs` / `activeTab`**: Read the current tab URL for chapter detection and tracking.
- **`alarms`**: Refresh unread badge on a schedule.
- **`contextMenus`**: Right-click “track this chapter”.
- **`<all_urls>` content script**: Reader sites live on many domains; the script only runs detection logic and talks to **your configured API** (and optionally MangaDex’s public API for metadata).

## Need help?

- Issues: use the repo’s GitHub Issues (see main README).
- Privacy policy text for store listing: `docs/EXTENSION_PRIVACY_POLICY.md`.
