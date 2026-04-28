# Manga/Manhwa Tracker

Track what you read across different manga/manhwa websites, detect new chapters, and keep your progress synced in one dashboard.

## What users get

- Auto-detect chapter pages while browsing.
- One-click series tracking.
- Last seen chapter + latest chapter links in dashboard.
- New update badges when a newer chapter is found.
- Account login and backup export/import support.

## For end users (Chrome)

### 1) Open your tracker dashboard

Use your hosted app URL (example: `https://your-app.onrender.com`).

### 2) Install the extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension` folder

### 3) Connect extension to your hosted backend

1. Click extension icon
2. In **Backend URL**, paste your hosted URL
3. Click **Save backend URL**
4. Click **Open dashboard** to verify connection

### 4) Start tracking

1. Visit a chapter page on a supported site
2. Accept the “Track this series?” prompt
3. Open dashboard and confirm series appears

## Account and data safety

- Users can create accounts and sign in from the dashboard.
- Use **Export Backup JSON** to download your data.
- Use **Import Backup** to restore/migrate data to another account or machine.

## Supported behavior

- Works best on chapter/reader pages (not generic homepages).
- Uses URL + title + DOM signals to detect chapters.
- Uses fast HTML scraping first; Selenium fallback is optional.

## If something is not working

- Confirm backend URL in extension popup is correct.
- Confirm hosted backend is healthy at `/healthz`.
- Enable extension Debug mode and share the debug output.
- If one site fails, share:
  - series URL
  - chapter URL
  - expected chapter number

## For developers / self-hosting

### Local run

```bash
pip install -r requirements.txt
python app.py
```

### Production run

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

Recommended env vars:

- `SECRET_KEY` (required)
- `FLASK_DEBUG=0`
- `DATABASE_URL` (Render PostgreSQL connection string)
- `USE_SELENIUM_FALLBACK=0`
- `MAX_CHECK_WORKERS=6`
- `HTTP_TIMEOUT_SECONDS=15`
