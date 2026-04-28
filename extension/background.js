const API_BASE = "http://127.0.0.1:5000";

async function postJson(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
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
        const stored = await chrome.storage.local.get(["autoprompt", "debugMode"]);
        sendResponse({
          ok: true,
          data: {
            autoprompt: stored.autoprompt !== false,
            debugMode: stored.debugMode === true,
          },
        });
        return;
      }
      if (msg?.type === "SET_AUTOPROMPT") {
        await chrome.storage.local.set({ autoprompt: !!msg.payload?.autoprompt });
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "SET_DEBUG_MODE") {
        await chrome.storage.local.set({ debugMode: !!msg.payload?.debugMode });
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "TRACK_DEBUG") {
        const events = await storeDebug(msg.payload || {});
        sendResponse({ ok: true, count: events.length });
        return;
      }
      if (msg?.type === "GET_DEBUG_EVENTS") {
        const stored = await chrome.storage.local.get(["debugEvents"]);
        sendResponse({ ok: true, data: Array.isArray(stored.debugEvents) ? stored.debugEvents : [] });
        return;
      }
      if (msg?.type === "MERGE_DUPLICATES") {
        const data = await postJson("/api/maintenance/merge-duplicates", {});
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
