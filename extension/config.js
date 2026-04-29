// Single source of truth for the Manga Tracker backend URL the companion talks to.
// Loaded by background.js (importScripts), popup.html, and options.html.
//
// Update PUBLIC_API_BASE here if you redeploy the Flask app under a new URL.
// Power users can still override per-install via the options page.
const PUBLIC_API_BASE = "https://manhwa-manga-tracking-through-out.onrender.com";
const DEFAULT_API_BASE = PUBLIC_API_BASE;
