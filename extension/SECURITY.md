# Extension security & privacy (plain language)

## What is **not** in this package

Publishing or downloading the extension **does not** expose:

- Your (or anyone’s) **passwords** or **phone numbers** — those are not stored in the extension source.
- **Database** credentials, **Flask `SECRET_KEY`**, **`ADMIN_API_TOKEN`**, or any other server secrets — those live only in your hosting provider’s environment (e.g. Render), never in `extension/`.
- Other users’ **private libraries** — there is no master key in the client.

If you audit this folder, you should only find HTML, JavaScript, icons, and the **public** hostname of the API (same idea as `api.example.com` for any SaaS product).

## How access to *your* data actually works

1. The **website / API** is meant to be reachable over HTTPS, like any web app.
2. **Private data** (bookmarks, progress) is behind a normal **logged-in session**: the browser holds an HTTP-only session cookie after you sign in on the dashboard.
3. The extension calls `/api/...` with **`credentials: "include"`**, so the **same** cookie is sent. No cookie → the API returns **401** and the extension tells you to sign in.
4. On the server, every request is tied to **that user’s account**. Someone else using a copy of the extension **cannot** see your library unless they know **your** username and password (same risk as any website—use a strong, unique password).

So: **open-sourcing the extension ≠ giving strangers access to your account.** It only documents how a signed-in browser talks to the API.

## Default API URL in `config.js`

The default base URL points at the **public** Manga Watchlist API. That hostname is intentionally public (browsers must connect to it). It does not grant administrative or cross-user access.

## Optional: custom / self-hosted backend

Users who set **Options → API base URL** to `http://127.0.0.1:5000` or their own domain are only configuring **their** browser. That does not open your production database or secrets; it only tells **their** extension where to send requests. Your production server should still enforce **HTTPS**, **strong secrets**, **CORS**, and **auth** as described in the main README.

## Reducing risk (operations checklist)

- Keep **`SECRET_KEY`**, **`DATABASE_URL`**, and **`ADMIN_API_TOKEN`** only in the host’s env UI, not in Git.
- In production, set **`CORS_ALLOW_ORIGINS`** and **`CHROME_EXTENSION_ID`** so only your dashboard and published extension origin can use credentialed API calls the way you intend.
- Use **`CONTACT_EMAIL`** / footer links via env vars if you don’t want to hardcode personal addresses in templates.

## Reporting issues

If you believe you found a security vulnerability, open a private channel if your project offers one, or file an issue with details (no live exploit code needed). For this repo, use GitHub Issues unless the maintainer publishes a security policy elsewhere.
