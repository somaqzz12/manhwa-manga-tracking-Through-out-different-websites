// `DEFAULT_API_BASE` comes from extension/config.js, loaded before this script in popup.html.
const $ = (id) => document.getElementById(id);

function sendMessage(msg) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response);
      });
    } catch (err) {
      resolve({ ok: false, error: String(err) });
    }
  });
}

let toastTimer = null;
function showToast(text, kind = "success") {
  const toast = $("toast");
  toast.textContent = text;
  toast.className = `toast ${kind}`;
  requestAnimationFrame(() => toast.classList.add("show"));
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function setStatus(text) {
  $("status").textContent = text || "";
}

function setLoading(isLoading) {
  $("loading").classList.toggle("hidden", !isLoading);
  $("content").classList.toggle("hidden", isLoading);
}

function showState(name) {
  for (const id of ["stateNotConfigured", "stateNoChapter", "stateChapter"]) {
    $(id).classList.toggle("hidden", id !== name);
  }
}

function setConnectionDot(state, label) {
  const dot = $("connDot");
  dot.classList.remove("green", "amber", "red");
  if (state) dot.classList.add(state);
  $("connText").textContent = label;
}

async function getActiveTabPageData() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return { ok: false, error: "No active tab" };
    if (tab.url && /^(chrome|edge|about|chrome-extension):/i.test(tab.url)) {
      return { ok: false, error: "Restricted page" };
    }
    const res = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_TRACK_DATA" });
    return res || { ok: false, error: "No response" };
  } catch (err) {
    return { ok: false, error: String(err?.message || err) };
  }
}

function openOptionsPage() {
  if (chrome.runtime.openOptionsPage) chrome.runtime.openOptionsPage();
  else chrome.tabs.create({ url: chrome.runtime.getURL("options.html") });
}

/** Match dashboard `normalize_bookmark_url`: trim, strip trailing slash, lower. */
function normListingUrl(u) {
  return String(u || "")
    .trim()
    .replace(/\/+$/, "")
    .toLowerCase();
}

function isSeriesTracked(data, trackedKeys, trackedUrlNorms) {
  if (data.seriesKey && trackedKeys.has(data.seriesKey)) return true;
  if (data.seriesUrl && trackedUrlNorms.has(normListingUrl(data.seriesUrl))) return true;
  return false;
}

async function init() {
  setLoading(true);
  setConnectionDot(null, "Checking...");

  const settingsRes = await sendMessage({ type: "GET_SETTINGS" });
  const apiBase = settingsRes?.ok ? settingsRes.data.apiBase : DEFAULT_API_BASE;
  const isConfigured = Boolean(apiBase);

  // Connection check + cached unread fetch in parallel with detection.
  const [healthRes, pageRes, unreadRes] = await Promise.all([
    sendMessage({ type: "HEALTH_CHECK" }),
    getActiveTabPageData(),
    sendMessage({ type: "UNREAD_COUNT" }),
  ]);

  if (healthRes?.ok) {
    setConnectionDot("green", "Connected");
  } else if (!isConfigured) {
    setConnectionDot("amber", "Not configured");
  } else {
    setConnectionDot("red", "Offline");
  }

  setLoading(false);

  if (!isConfigured || !healthRes?.ok) {
    showState("stateNotConfigured");
    $("notConfiguredMessage").textContent = !isConfigured
      ? "Add your backend URL in settings, then come back."
      : `Backend at ${apiBase} did not respond. Check it's running and try again.`;
    bindFooter();
    return;
  }

  const trackedKeys = new Set(unreadRes?.data?.tracked_keys || []);
  const trackedUrlNorms = new Set(unreadRes?.data?.tracked_url_norms || []);
  const totalUnread = Number(unreadRes?.data?.unread || 0);

  if (!pageRes?.ok || !pageRes?.data) {
    showState("stateNoChapter");
    if (totalUnread > 0) {
      $("noChapterUnread").classList.remove("hidden");
      $("noChapterUnreadValue").textContent = String(totalUnread);
    }
    const forceBtn = $("forceTrackButton");
    if (forceBtn) {
      forceBtn.addEventListener("click", async () => {
        forceBtn.disabled = true;
        setStatus("Saving...");
        const result = await sendMessage({ type: "TRACK_TAB_NOW", force: true });
        if (result?.ok) {
          setStatus("Saved.");
          showToast("Saved to tracker", "success");
          forceBtn.textContent = "Saved";
          setTimeout(() => init(), 900);
        } else {
          setStatus(`Failed: ${result?.error || "unknown error"}`);
          showToast(result?.error || "Failed to save", "error");
          forceBtn.disabled = false;
        }
      });
    }
    bindFooter();
    return;
  }

  const data = pageRes.data;
  showState("stateChapter");
  $("seriesTitle").textContent = data.title || "Untitled series";
  const chapterText = data.chapterNum != null
    ? `Chapter ${data.chapterNum}`
    : data.chapterLabel || "Detected chapter";
  $("chapterMeta").textContent = chapterText;

  const isTracked = isSeriesTracked(data, trackedKeys, trackedUrlNorms);
  const trackBtn = $("trackButton");
  if (isTracked) {
    $("trackedBadge").classList.remove("hidden");
    trackBtn.textContent = "Already tracked — save this chapter";
  } else {
    trackBtn.textContent = "Track now";
  }

  trackBtn.addEventListener("click", async () => {
    trackBtn.disabled = true;
    setStatus("Saving...");
    const result = await sendMessage({ type: "TRACK_TAB_NOW" });
    if (result?.ok) {
      setStatus("Saved.");
      showToast("Saved to tracker", "success");
      $("trackedBadge").classList.remove("hidden");
      trackBtn.textContent = "Saved";
      setTimeout(() => {
        trackBtn.disabled = false;
        trackBtn.textContent = "Save again";
      }, 1200);
    } else {
      setStatus(`Failed: ${result?.error || "unknown error"}`);
      showToast(result?.error || "Failed to save", "error");
      trackBtn.disabled = false;
    }
  });

  bindFooter();
}

function bindFooter() {
  $("openOptions")?.addEventListener("click", openOptionsPage);
  $("openOptionsFooter")?.addEventListener("click", openOptionsPage);
  $("openDashboard")?.addEventListener("click", async () => {
    const settingsRes = await sendMessage({ type: "GET_SETTINGS" });
    const base = (settingsRes?.data?.apiBase || DEFAULT_API_BASE).replace(/\/$/, "");
    chrome.tabs.create({ url: `${base}/` });
  });
}

init();
