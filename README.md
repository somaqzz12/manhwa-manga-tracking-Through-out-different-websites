# Manga/Manhwa Update Tracker

## Why you got `ERR_CONNECTION_REFUSED`

Most likely cause: nothing is running on `127.0.0.1:5000` right now (Flask app not started or crashed on startup).

## Fastest checks

1. Start the app and confirm you see: `Running on http://127.0.0.1:5000`
2. If it exits, reinstall dependencies:
   - `pip install -r requirements.txt`
3. Check if another process owns the port:
   - PowerShell: `netstat -ano | findstr :5000`
4. If occupied, stop that PID or run this app on a different port.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Selenium fallback (added)

- Enabled by default: `USE_SELENIUM_FALLBACK=1`
- Behavior: try BeautifulSoup first, then Selenium for JS-heavy sites when the first attempt fails.
- Disable in PowerShell:
  - `$env:USE_SELENIUM_FALLBACK='0'`

## Chrome extension (auto tracking)

Folder: `manga-tracker/extension`

What it does:
- Detects current page as a potential chapter page.
- Prompts: "Track this series?"
- Adds the series to dashboard through local API.
- Saves read progress immediately.

Load it:
1. Open `chrome://extensions`
2. Enable Developer mode
3. Click "Load unpacked"
4. Select `manga-tracker/extension`

Notes:
- Browser extensions cannot reliably read `HttpOnly` cookies from manga sites, so "use cookies directly" is limited by browser security.
- This extension tracks behavior from page URL/title instead, which is the stable way for this use case.
