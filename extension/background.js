const DEFAULT_API_BASE = "http://127.0.0.1:5000";

async function getApiBase() {
  const stored = await chrome.storage.local.get(["apiBase"]);
  const raw = (stored.apiBase || DEFAULT_API_BASE).trim();
  return raw.replace(/\/$/, "");
}

async function postJson(path, payload) {
  const apiBase = await getApiBase();
  const res = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  return data;
}

async function storeDebug(payload) {
  const previous = await chrome.storage.local.get(["debugEvents"]);
  const events = Array.isArray(previous.debugEvents) ? previous.debugEvents : [];
  events.push(payload);
  const trimmed = events.slice(-25);
  await chrome.storage.local.set({ debugEvents: trimmed });
  return trimmed;
}

async function trackPayload(payload) {
  const ensure = await postJson("/api/series/ensure", {
    title: payload.title,
    url: payload.seriesUrl,
    series_key: payload.seriesKey,
  });
  const progress = await postJson("/api/progress", {
    series_url: payload.seriesUrl,
    series_key: payload.seriesKey,
    chapter_url: payload.chapterUrl,
    chapter_label: payload.chapterLabel,
    chapter_num: payload.chapterNum,
  });
  return { ensure, progress };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg?.type === "ENSURE_SERIES") {
        const data = await postJson("/api/series/ensure", msg.payload);
        sendResponse({ ok: true, data });
        return;
      }
      if (msg?.type === "SAVE_PROGRESS") {
        const data = await postJson("/api/progress", msg.payload);
        sendResponse({ ok: true, data });
        return;
      }
      if (msg?.type === "GET_SETTINGS") {
        const stored = await chrome.storage.local.get(["apiBase"]);
        sendResponse({
          ok: true,
          data: {
            apiBase: stored.apiBase || DEFAULT_API_BASE,
          },
        });
        return;
      }
      if (msg?.type === "SET_API_BASE") {
        const raw = (msg.payload?.apiBase || DEFAULT_API_BASE).trim().replace(/\/$/, "");
        await chrome.storage.local.set({ apiBase: raw });
        sendResponse({ ok: true, apiBase: raw });
        return;
      }
      if (msg?.type === "TRACK_TAB_NOW") {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab?.id) {
          sendResponse({ ok: false, error: "No active tab found." });
          return;
        }
        const pageRes = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_TRACK_DATA" });
        if (!pageRes?.ok || !pageRes?.data) {
          sendResponse({ ok: false, error: "This page is not recognized as a chapter page." });
          return;
        }
        const data = await trackPayload(pageRes.data);
        sendResponse({ ok: true, data });
        return;
      }
      sendResponse({ ok: false, error: "Unknown message" });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});
