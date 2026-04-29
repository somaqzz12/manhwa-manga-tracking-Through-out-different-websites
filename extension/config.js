// Single source of truth for the Manga Tracker backend URL the companion talks to.
// Loaded by background.js (importScripts), popup.html, and options.html.
//
// Update PUBLIC_API_BASE if your Render (or other) service is named differently.
// Leaving it on https://manga-tracker.onrender.com matches the included render.yaml,
// where the service is named "manga-tracker".
const PUBLIC_API_BASE = "https://manga-tracker.onrender.com";
const DEFAULT_API_BASE = PUBLIC_API_BASE;
