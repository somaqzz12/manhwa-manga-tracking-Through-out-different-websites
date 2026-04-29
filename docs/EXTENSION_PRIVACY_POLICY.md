# Privacy policy — Manga Tracker Companion (Chrome extension)

**Last updated:** April 29, 2026

This policy describes the **Manga Tracker Companion** browser extension published from the open-source project at  
https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites

## What the extension does

The extension helps you sync manga and manhwa **reading progress** to your **Manga Tracker** account. By default it talks to the official Manga Tracker server at `https://manhwa-manga-tracking-through-out.onrender.com`. Advanced users can point the extension at a different deployment from the options page. The extension does not replace a publisher’s website and does not host manga content.

## Data the extension collects

The extension **does not** sell, rent, or trade personal data. It **does not** include third-party analytics or advertising SDKs.

### Stored on your device (local only)

- **Settings** you enter (for example your tracker’s base URL, auto-track preferences, prompt cooldown) are kept in `chrome.storage.local` on your machine.
- A small **debug log** (at most the last 25 events) is stored locally to help you troubleshoot sync issues.

### Sent to servers

- **Your Manga Tracker server only.** When you save progress or refresh the unread badge, the extension sends HTTP requests **only to the configured backend URL** (default: `https://manhwa-manga-tracking-through-out.onrender.com`). Those requests may include chapter URLs, series titles, and numeric chapter identifiers your tracker needs to update bookmarks.
- **MangaDex (optional, read-only metadata).** On `mangadex.org` chapter pages, the extension may call the public MangaDex API (`api.mangadex.org`) to read chapter and series metadata (titles, chapter numbers). No MangaDex account is required for that call, and the extension does not send your Manga Tracker credentials to MangaDex.

The extension **does not** send your reading activity to the extension author or to any other third party.

## Permissions (why they exist)

| Permission | Purpose |
| --- | --- |
| `storage` | Save your backend URL and preferences locally. |
| `activeTab` | Read the current tab when you use the popup, shortcut, or context menu to track a chapter. |
| `tabs` | Find the active tab to message the content script. |
| `alarms` | Wake the background worker periodically to refresh the unread chapter badge. |
| `contextMenus` | Provide “Track this manga chapter” in the right-click menu. |
| **Host access `<all_urls>`** | Manga and manhwa readers use many different domains. The content script only runs detection logic on pages you visit; network calls from the extension go to **your** configured tracker (and, on MangaDex chapter pages, the public MangaDex API as described above). |

## Session / sign-in

If your tracker requires login, you sign in **in the browser** on your tracker’s website. The extension reuses that session (cookies) when calling your tracker’s API, the same way the dashboard would. The extension author cannot access your password or session.

## Your choices

- You can **uninstall** the extension at any time; that removes the extension’s local storage from Chrome’s extension data.
- You can **clear local data** from the extension’s Settings (options) page without uninstalling.

## Open source

The extension source code is available in the repository linked above. If you have questions or requests, use the project’s **Issues** page on GitHub.

## Contact

Use the repository **Issues** tab:  
https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues
