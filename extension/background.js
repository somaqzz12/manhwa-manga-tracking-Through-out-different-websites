// Loads `DEFAULT_API_BASE` (and `PUBLIC_API_BASE`) into the service worker scope.
// Edit extension/config.js to point the companion at a different deployment.
importScripts("config.js");
const DEFAULT_COOLDOWN_HOURS = 24;
const UNREAD_ALARM_NAME = "manga-watchlist-unread-poll";
const UNREAD_POLL_PERIOD_MINUTES = 30;
const KEEPALIVE_ALARM_NAME = "manga-watchlist-keepalive-ping";
const KEEPALIVE_PERIOD_MINUTES = 5;
const CONTEXT_MENU_ID = "manga-watchlist-track-chapter";
const TRACK_COMMAND = "track-current-chapter";
const DEBUG_LOG_LIMIT = 25;

function normalizeApiBase(raw) {
  const clean = String(raw || "").trim().replace(/\/$/, "");
  if (clean === LEGACY_PUBLIC_API_BASE) return PUBLIC_API_BASE;
  return clean;
}

async function getSettings() {
  const stored = await chrome.storage.local.get([
    "apiBase",
    "autoTrack",
    "cooldownHours",
  ]);
  const originalApiBase = stored.apiBase || DEFAULT_API_BASE;
  const apiBaseRaw = normalizeApiBase(originalApiBase);
  if (stored.apiBase && apiBaseRaw !== stored.apiBase.trim().replace(/\/$/, "")) {
    await chrome.storage.local.set({ apiBase: apiBaseRaw });
  }
  return {
    apiBase: apiBaseRaw,
    autoTrack: Boolean(stored.autoTrack),
    cooldownHours: Number.isFinite(stored.cooldownHours)
      ? stored.cooldownHours
      : DEFAULT_COOLDOWN_HOURS,
  };
}

async function getApiBase() {
  const { apiBase } = await getSettings();
  return apiBase;
}

async function postJson(path, payload) {
  const apiBase = await getApiBase();
  // credentials: "include" forwards the Manga Watchlist session cookie when the
  // user is signed in on the dashboard; /api/* routes require that session.
  const res = await fetch(`${apiBase}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error(
        "Not signed in. Open the dashboard, sign in, then try tracking again."
      );
    }
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  return data;
}

async function getJson(path) {
  const apiBase = await getApiBase();
  const res = await fetch(`${apiBase}${path}`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Not signed in.");
    }
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  return data;
}

async function storeDebug(payload) {
  const enriched = {
    at: new Date().toISOString(),
    level: "info",
    ...payload,
  };
  const previous = await chrome.storage.local.get(["debugEvents"]);
  const events = Array.isArray(previous.debugEvents) ? previous.debugEvents : [];
  events.push(enriched);
  const trimmed = events.slice(-DEBUG_LOG_LIMIT);
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

async function fetchUnreadAndUpdateBadge() {
  try {
    const data = await getJson("/api/unread-count");
    const unread = Number(data?.unread || 0);
    await setBadge(unread);
    await chrome.storage.local.set({
      lastUnread: {
        unread,
        behind: Number(data?.behind || 0),
        trackedKeys: Array.isArray(data?.tracked_keys) ? data.tracked_keys : [],
        at: Date.now(),
      },
    });
    return data;
  } catch (err) {
    await storeDebug({
      type: "unread_poll_failed",
      level: "error",
      error: String(err?.message || err),
    });
    await setBadge(0);
    throw err;
  }
}

async function setBadge(unread) {
  const text = unread > 0 ? (unread > 99 ? "99+" : String(unread)) : "";
  try {
    await chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });
    if (chrome.action.setBadgeTextColor) {
      await chrome.action.setBadgeTextColor({ color: "#ffffff" });
    }
    await chrome.action.setBadgeText({ text });
  } catch {}
}

async function requestPageTrackData(tabId, force) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: "GET_PAGE_TRACK_DATA",
      force,
    });
  } catch (err) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["content.js"],
      });
      return await chrome.tabs.sendMessage(tabId, {
        type: "GET_PAGE_TRACK_DATA",
        force,
      });
    } catch (injectErr) {
      throw new Error(injectErr?.message || err?.message || String(injectErr || err));
    }
  }
}

async function ensureUnreadAlarm() {
  const existing = await chrome.alarms.get(UNREAD_ALARM_NAME);
  if (!existing) {
    chrome.alarms.create(UNREAD_ALARM_NAME, {
      delayInMinutes: 1,
      periodInMinutes: UNREAD_POLL_PERIOD_MINUTES,
    });
  }
}

async function ensureKeepAliveAlarm() {
  const existing = await chrome.alarms.get(KEEPALIVE_ALARM_NAME);
  if (!existing) {
    chrome.alarms.create(KEEPALIVE_ALARM_NAME, {
      delayInMinutes: 1,
      periodInMinutes: KEEPALIVE_PERIOD_MINUTES,
    });
  }
}

async function pingHealthzKeepAlive() {
  try {
    const apiBase = await getApiBase();
    await fetch(`${apiBase}/healthz`, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
    });
  } catch {
    // Keep-alive pings are best-effort; avoid noisy failures.
  }
}

function ensureContextMenu() {
  try {
    chrome.contextMenus.removeAll(() => {
      chrome.contextMenus.create({
        id: CONTEXT_MENU_ID,
        title: "Track this manga chapter",
        contexts: ["page", "link"],
      });
    });
  } catch {}
}

async function trackActiveTab({ force = false } = {}) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return { ok: false, error: "No active tab found." };
  let pageRes;
  try {
    pageRes = await requestPageTrackData(tab.id, force);
  } catch (err) {
    return { ok: false, error: `Content script unavailable: ${err?.message || err}` };
  }
  if (!pageRes?.ok || !pageRes?.data) {
    return {
      ok: false,
      error: force
        ? "Could not read this page. Try refreshing it and tracking again."
        : "This page is not recognized as a chapter page.",
    };
  }
  try {
    const data = await trackPayload(pageRes.data);
    await storeDebug({
      type: force ? "manual_track_force_ok" : "manual_track_ok",
      message: pageRes.data.title || "(untitled)",
    });
    fetchUnreadAndUpdateBadge().catch(() => {});
    return { ok: true, data };
  } catch (err) {
    await storeDebug({
      type: force ? "manual_track_force_failed" : "manual_track_failed",
      level: "error",
      error: String(err?.message || err),
    });
    return { ok: false, error: String(err?.message || err) };
  }
}

async function broadcastClearPageSnoozes() {
  try {
    const tabs = await chrome.tabs.query({});
    await Promise.all(
      tabs.map((tab) =>
        tab.id != null
          ? chrome.tabs
              .sendMessage(tab.id, { type: "CLEAR_PAGE_SNOOZES_CONTENT" })
              .catch(() => {})
          : Promise.resolve()
      )
    );
  } catch {}
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
        fetchUnreadAndUpdateBadge().catch(() => {});
        sendResponse({ ok: true, data });
        return;
      }
      if (msg?.type === "GET_SETTINGS") {
        const settings = await getSettings();
        sendResponse({ ok: true, data: settings });
        return;
      }
      if (msg?.type === "SET_API_BASE") {
        const raw = normalizeApiBase(msg.payload?.apiBase || DEFAULT_API_BASE);
        await chrome.storage.local.set({ apiBase: raw });
        sendResponse({ ok: true, apiBase: raw });
        return;
      }
      if (msg?.type === "TRACK_TAB_NOW") {
        const result = await trackActiveTab({ force: Boolean(msg.force) });
        sendResponse(result);
        return;
      }
      if (msg?.type === "HEALTH_CHECK") {
        const apiBase = await getApiBase();
        try {
          const res = await fetch(`${apiBase}/healthz`, {
            method: "GET",
            credentials: "include",
            cache: "no-store",
          });
          sendResponse({ ok: res.ok, status: res.status, apiBase });
        } catch (err) {
          sendResponse({ ok: false, error: String(err?.message || err), apiBase });
        }
        return;
      }
      if (msg?.type === "UNREAD_COUNT") {
        try {
          const data = await fetchUnreadAndUpdateBadge();
          sendResponse({ ok: true, data });
        } catch (err) {
          sendResponse({ ok: false, error: String(err?.message || err) });
        }
        return;
      }
      if (msg?.type === "CLEAR_PAGE_SNOOZES") {
        await broadcastClearPageSnoozes();
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "MANGADEX_FETCH") {
        const uuid = String(msg.payload?.uuid || "").trim();
        if (!/^[0-9a-f-]{8,}$/i.test(uuid)) {
          sendResponse({ ok: false, error: "Invalid MangaDex chapter UUID" });
          return;
        }
        try {
          const res = await fetch(
            `https://api.mangadex.org/chapter/${uuid}?includes[]=manga`,
            { method: "GET", credentials: "omit", cache: "no-store" }
          );
          const json = await res.json().catch(() => ({}));
          if (!res.ok) {
            sendResponse({ ok: false, error: `MangaDex HTTP ${res.status}` });
            return;
          }
          const data = json?.data;
          const chapterAttributes = data?.attributes || {};
          const relationships = data?.relationships || [];
          const mangaRel = relationships.find((r) => r.type === "manga");
          sendResponse({
            ok: true,
            data: {
              id: data?.id,
              chapter: chapterAttributes.chapter,
              chapterAttributes,
              attributes: mangaRel?.attributes || {},
              relationships,
            },
          });
        } catch (err) {
          sendResponse({ ok: false, error: String(err?.message || err) });
        }
        return;
      }
      sendResponse({ ok: false, error: "Unknown message" });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === UNREAD_ALARM_NAME) {
    fetchUnreadAndUpdateBadge().catch(() => {});
    return;
  }
  if (alarm.name === KEEPALIVE_ALARM_NAME) {
    pingHealthzKeepAlive().catch(() => {});
  }
});

chrome.runtime.onInstalled.addListener(() => {
  ensureContextMenu();
  ensureUnreadAlarm();
  ensureKeepAliveAlarm();
  pingHealthzKeepAlive().catch(() => {});
  fetchUnreadAndUpdateBadge().catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  ensureContextMenu();
  ensureUnreadAlarm();
  ensureKeepAliveAlarm();
  pingHealthzKeepAlive().catch(() => {});
  fetchUnreadAndUpdateBadge().catch(() => {});
});

// Service workers can be torn down between events; re-establish menu/alarm
// idempotently every time the worker spins up.
ensureContextMenu();
ensureUnreadAlarm();
ensureKeepAliveAlarm();

if (chrome.contextMenus?.onClicked) {
  chrome.contextMenus.onClicked.addListener((info, _tab) => {
    if (info.menuItemId !== CONTEXT_MENU_ID) return;
    trackActiveTab().then((result) => {
      if (!result.ok) {
        storeDebug({
          type: "context_menu_track_failed",
          level: "error",
          error: result.error || "unknown",
        }).catch(() => {});
      }
    });
  });
}

if (chrome.commands?.onCommand) {
  chrome.commands.onCommand.addListener((command) => {
    if (command !== TRACK_COMMAND) return;
    trackActiveTab().then((result) => {
      if (!result.ok) {
        storeDebug({
          type: "shortcut_track_failed",
          level: "error",
          error: result.error || "unknown",
        }).catch(() => {});
      }
    });
  });
}
