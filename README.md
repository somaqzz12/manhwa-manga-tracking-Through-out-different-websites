# Manga/Manhwa Update Tracker

Track manga/manhwa progress across many reader sites with a Flask backend + Chrome extension.

## Local Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Production Run

Use Gunicorn:

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

Recommended environment variables:

- `SECRET_KEY` (required in production)
- `FLASK_DEBUG=0`
- `PORT` (set by host, defaults to `5000`)
- `USE_SELENIUM_FALLBACK=0` (usually disable for hosted free tiers)
- `MAX_CHECK_WORKERS=6`
- `HTTP_TIMEOUT_SECONDS=15`

## Deploy (Render quick start)

1. Create a new **Web Service** from your GitHub repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn -w 2 -b 0.0.0.0:$PORT app:app`
4. Set env vars (`SECRET_KEY`, etc.).
5. Deploy and copy your live URL (e.g. `https://your-app.onrender.com`).

## Extension Setup

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click **Load unpacked**
4. Select the `extension` folder
5. Open extension popup and set **Backend URL** to your deployed API (or local `http://127.0.0.1:5000`)

## Notes

- Extension tracks chapter pages via URL/title/DOM signals.
- Selenium is fallback-only when enabled.
- Account + export/import backup are available in dashboard UI.
