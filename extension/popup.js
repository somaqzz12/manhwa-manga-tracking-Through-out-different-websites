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

function isSafeHttpUrl(raw) {
  if (!raw || typeof raw !== "string") return false;
  try {
    const u = new URL(raw);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function makePreviewLine(label, value) {
  const row = document.createElement("div");
  row.className = "preview-line";
  row.textContent = `${label}: ${value || "-"}`;
  return row;
}

function createCoverPlaceholder() {
  const box = document.createElement("div");
  box.className = "preview-cover-placeholder";
  box.textContent = "MW";
  return box;
}

let lastPreview = null;
let lastTabUrl = "";
let lastPageData = null;

function bindPreview(apiBase) {
  const previewBtn = $("previewButton");
  if (!previewBtn || previewBtn.dataset.bound === "1") return;
  previewBtn.dataset.bound = "1";
  previewBtn.addEventListener("click", async () => {
    previewBtn.disabled = true;
    setStatus("Resolving page URL...");
    const targetUrl = (lastPageData?.chapterUrl || lastPageData?.seriesUrl || lastTabUrl || "").trim();
    if (!isSafeHttpUrl(targetUrl)) {
      setStatus("No valid page URL found in current tab.");
      previewBtn.disabled = false;
      return;
    }
    const res = await sendMessage({ type: "RESOLVE_URL", payload: { url: targetUrl } });
    if (!res?.ok || !res.data?.ok) {
      setStatus(res?.error || res?.data?.error || "Resolver preview failed.");
      previewBtn.disabled = false;
      return;
    }
    renderResolverPreview(res.data, apiBase);
    const supportLevel = String(res.data.support_level || "");
    if (supportLevel.toLowerCase() === "manual_only") {
      setStatus("Manual-only source: add with a title to track.");
    } else {
      setStatus("Preview ready.");
    }
    previewBtn.disabled = false;
  });
}

async function getActiveTabUrl() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return String(tab?.url || "");
  } catch {
    return "";
  }
}

function renderResolverPreview(preview, apiBase) {
  const host = $("previewHost");
  host.replaceChildren();
  host.classList.remove("hidden");
  lastPreview = preview;

  const top = document.createElement("div");
  top.className = "preview-row";

  if (isSafeHttpUrl(preview.cover_url || "")) {
    const img = document.createElement("img");
    img.className = "preview-cover";
    img.alt = "";
    img.src = preview.cover_url;
    img.addEventListener("error", () => {
      img.replaceWith(createCoverPlaceholder());
    });
    top.appendChild(img);
  } else {
    top.appendChild(createCoverPlaceholder());
  }

  const details = document.createElement("div");
  details.style.flex = "1";
  const title = document.createElement("div");
  title.className = "preview-title";
  title.textContent = preview.canonical_title || preview.title || "Unknown title";
  details.appendChild(title);
  details.appendChild(makePreviewLine("Source", preview.source_name || "Manual"));
  details.appendChild(makePreviewLine("Support", preview.support_level || "-"));
  details.appendChild(makePreviewLine("Latest", preview.latest_chapter || "Unknown"));
  if (preview.description) details.appendChild(makePreviewLine("Description", preview.description));
  top.appendChild(details);
  host.appendChild(top);

  const warnings = Array.isArray(preview.warnings) ? preview.warnings : [];
  if (warnings.length) {
    const list = document.createElement("ul");
    list.className = "warn-list";
    for (const warning of warnings) {
      const li = document.createElement("li");
      li.textContent = String(warning || "");
      list.appendChild(li);
    }
    host.appendChild(list);
  }

  const manualOnly = String(preview.support_level || "").toLowerCase() === "manual_only";
  let manualTitleInput = null;
  let requestSupportBtn = null;
  if (manualOnly) {
    const manualNote = document.createElement("div");
    manualNote.className = "manual-note";
    manualNote.textContent =
      "Manual tracking only. We can save this URL, but automatic chapter checks are not available for this source yet.";
    host.appendChild(manualNote);
  }
  if (manualOnly && !String(preview.title || "").trim()) {
    manualTitleInput = document.createElement("input");
    manualTitleInput.className = "input-mini";
    manualTitleInput.id = "manualPreviewTitle";
    manualTitleInput.placeholder = "Title required for manual tracking";
    host.appendChild(manualTitleInput);
  }

  const row = document.createElement("div");
  row.className = "footer-links";
  row.style.marginTop = "10px";
  const addBtn = document.createElement("button");
  addBtn.textContent = "Add to Library";
  const openDash = document.createElement("button");
  openDash.className = "secondary";
  openDash.textContent = "Open Dashboard";
  row.appendChild(addBtn);
  if (manualOnly) {
    requestSupportBtn = document.createElement("button");
    requestSupportBtn.className = "secondary";
    requestSupportBtn.textContent = "Request source support";
    row.appendChild(requestSupportBtn);
  } else {
    row.appendChild(openDash);
  }
  host.appendChild(row);

  addBtn.addEventListener("click", async () => {
    addBtn.disabled = true;
    const payload = {
      url: preview.source_url || lastTabUrl || "",
      title: preview.title || "",
      canonical_title: preview.canonical_title || "",
      description: preview.description || "",
      chapter_count: preview.chapter_count || "",
      cover_url: preview.cover_url || "",
      latest_chapter: preview.latest_chapter || "",
      support_level: preview.support_level || "manual_only",
      source_name: preview.source_name || "",
    };
    if (manualTitleInput) {
      const forcedTitle = manualTitleInput.value.trim();
      if (!forcedTitle) {
        setStatus("Manual sources require a title.");
        addBtn.disabled = false;
        return;
      }
      payload.title = forcedTitle;
    }
    const res = await sendMessage({ type: "ADD_FROM_PREVIEW", payload });
    if (!res?.ok || !res.data?.ok) {
      const errMsg = String(res?.error || res?.data?.error || "Could not add to library.");
      if (/not signed in|authentication required|sign in/i.test(errMsg)) {
        setStatus("Sign in first. Open Manga Watchlist, sign in, then try again.");
        row.replaceChildren();
        const openAppBtn = document.createElement("button");
        openAppBtn.className = "secondary";
        openAppBtn.textContent = "Open app";
        row.appendChild(openAppBtn);
        openAppBtn.addEventListener("click", () => chrome.tabs.create({ url: `${apiBase}/` }));
      } else {
        setStatus(errMsg);
      }
      addBtn.disabled = false;
      return;
    }
    setStatus("Added to library.");
    showToast("Added to library", "success");
    row.replaceChildren();
    const dash = document.createElement("button");
    dash.className = "secondary";
    dash.textContent = "Open Dashboard";
    const lib = document.createElement("button");
    lib.className = "secondary";
    lib.textContent = "View Library";
    row.appendChild(dash);
    row.appendChild(lib);
    const openLibrary = () => chrome.tabs.create({ url: `${apiBase}/app` });
    dash.addEventListener("click", () => chrome.tabs.create({ url: `${apiBase}/` }));
    lib.addEventListener("click", openLibrary);
  });

  openDash.addEventListener("click", () => chrome.tabs.create({ url: `${apiBase}/` }));
  requestSupportBtn?.addEventListener("click", () => chrome.tabs.create({ url: `${apiBase}/source-requests` }));
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
  const [healthRes, pageRes, unreadRes, tabUrl] = await Promise.all([
    sendMessage({ type: "HEALTH_CHECK" }),
    getActiveTabPageData(),
    sendMessage({ type: "UNREAD_COUNT" }),
    getActiveTabUrl(),
  ]);
  lastTabUrl = tabUrl;
  lastPageData = pageRes?.data || null;

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
  bindPreview(apiBase);

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
  const markReadBtn = $("markReadButton");
  if (isTracked) {
    $("trackedBadge").classList.remove("hidden");
    trackBtn.textContent = "Track this page";
    if (markReadBtn) markReadBtn.disabled = false;
  } else {
    trackBtn.textContent = "Track this page";
    if (markReadBtn) markReadBtn.disabled = true;
    setStatus("Track this page first to connect it to your library.");
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

  markReadBtn?.addEventListener("click", async () => {
    if (!isTracked) {
      setStatus("Track this page first to connect it to your library.");
      return;
    }
    markReadBtn.disabled = true;
    setStatus("Saving current chapter...");
    const result = await sendMessage({ type: "TRACK_TAB_NOW" });
    if (result?.ok) {
      setStatus("Current chapter marked as read.");
      showToast("Chapter progress updated", "success");
    } else {
      setStatus(`Failed: ${result?.error || "unknown error"}`);
      showToast(result?.error || "Failed to save chapter", "error");
    }
    markReadBtn.disabled = false;
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
