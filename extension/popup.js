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

function formatSupportLabel(raw) {
  const s = String(raw || "").toLowerCase();
  if (s === "official_api") return "Automatic";
  if (s === "site_adapter") return "Supported";
  if (s === "generic_detector") return "Experimental";
  if (s === "extension_assisted") return "Extension-assisted";
  if (s === "manual_only" || s === "manual") return "Manual";
  if (s === "blocked") return "Unavailable";
  if (s === "requested") return "Extension-assisted";
  return raw || "—";
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

function toCanonicalPreviewShape(raw, fallbackUrl = "") {
  const src = raw && typeof raw === "object" ? raw : {};
  return {
    source_url: String(src.source_url || src.url || fallbackUrl || "").trim(),
    source_name: String(src.source_name || "Manual").trim(),
    source_domain: String(src.source_domain || "").trim(),
    support_level: String(src.support_level || "manual_only").trim(),
    title: String(src.title || "").trim(),
    canonical_title: String(src.canonical_title || "").trim(),
    description: String(src.description || "").trim(),
    cover_url: String(src.cover_url || "").trim(),
    latest_chapter: String(src.latest_chapter || "").trim(),
    current_chapter: String(src.current_chapter || "").trim(),
    chapter_count: src.chapter_count ?? "",
    chapters: Array.isArray(src.chapters) ? src.chapters : [],
    warnings: Array.isArray(src.warnings) ? src.warnings : [],
    detection_source: String(src.detection_source || "manual").trim(),
    confidence: src.confidence ?? 0,
  };
}

function buildExtensionAssistedPreview(basePreview, pageData, fallbackUrl) {
  const backend = toCanonicalPreviewShape(basePreview, fallbackUrl);
  const data = pageData && typeof pageData === "object" ? pageData : {};
  const hasDetected =
    Boolean(String(data.title || "").trim()) ||
    Boolean(String(data.coverUrl || "").trim()) ||
    data.chapterNum != null;
  if (!hasDetected) return backend;
  const sourceUrl = String(data.seriesUrl || data.chapterUrl || backend.source_url || fallbackUrl || "").trim();
  const sourceDomain =
    String(data.sourceDomain || "").trim() ||
    (() => {
      try {
        return new URL(sourceUrl).hostname.replace(/^www\./i, "").toLowerCase();
      } catch {
        return backend.source_domain || "";
      }
    })();
  const confidenceRaw = String(data.detectionConfidence || "").toLowerCase();
  const confidence = confidenceRaw === "high" ? 0.92 : confidenceRaw === "medium" ? 0.7 : 0.5;
  const latestChapter = data.chapterNum != null ? String(data.chapterNum) : backend.latest_chapter;
  return {
    ...backend,
    source_url: sourceUrl || backend.source_url,
    source_name: backend.source_name || sourceDomain || "Manual",
    source_domain: sourceDomain,
    support_level: "extension_assisted",
    title: String(data.title || backend.title || "").trim(),
    canonical_title: String(data.title || backend.canonical_title || "").trim(),
    description: String(data.description || backend.description || "").trim(),
    cover_url: String(data.coverUrl || backend.cover_url || "").trim(),
    latest_chapter: latestChapter,
    current_chapter: latestChapter,
    detection_source: "extension",
    confidence: confidence,
    warnings: [
      "Detected from your browser. Automatic backend checks may be limited.",
      ...(backend.warnings || []),
    ],
  };
}

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
    const canonical = toCanonicalPreviewShape(res.data, targetUrl);
    const supportLevel = String(canonical.support_level || "").toLowerCase();
    const finalPreview =
      supportLevel === "manual_only"
        ? buildExtensionAssistedPreview(canonical, lastPageData, targetUrl)
        : canonical;
    renderResolverPreview(finalPreview, apiBase);
    if (String(finalPreview.support_level || "").toLowerCase() === "manual_only") {
      setStatus("Manual tracking only.");
    } else if (String(finalPreview.support_level || "").toLowerCase() === "extension_assisted") {
      setStatus("Detected from browser.");
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
  const shaped = toCanonicalPreviewShape(preview, lastTabUrl);
  lastPreview = shaped;

  const top = document.createElement("div");
  top.className = "preview-row";

  if (isSafeHttpUrl(shaped.cover_url || "")) {
    const img = document.createElement("img");
    img.className = "preview-cover";
    img.alt = "";
    img.src = shaped.cover_url;
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
  title.textContent = shaped.canonical_title || shaped.title || "Unknown title";
  details.appendChild(title);
  details.appendChild(makePreviewLine("Source", shaped.source_name || shaped.source_domain || "Manual"));
  details.appendChild(makePreviewLine("Support", formatSupportLabel(shaped.support_level)));
  details.appendChild(makePreviewLine("Latest", shaped.latest_chapter || "Unknown"));
  if (shaped.description) details.appendChild(makePreviewLine("Description", shaped.description));
  top.appendChild(details);
  host.appendChild(top);

  const warnings = Array.isArray(shaped.warnings) ? shaped.warnings : [];
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

  const level = String(shaped.support_level || "").toLowerCase();
  const manualOnly = level === "manual_only";
  const extensionAssisted = level === "extension_assisted";
  let manualTitleInput = null;
  let requestSupportBtn = null;
  if (extensionAssisted) {
    const extNote = document.createElement("div");
    extNote.className = "manual-note";
    extNote.textContent = "Detected from browser. Automatic backend checks may be limited.";
    host.appendChild(extNote);
  }
  if (manualOnly) {
    const manualNote = document.createElement("div");
    manualNote.className = "manual-note";
    manualNote.textContent =
      "Manual tracking only. We can save this URL, but automatic chapter checks are not available for this source yet.";
    host.appendChild(manualNote);
  }
  if (manualOnly && !String(shaped.title || "").trim()) {
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
  addBtn.type = "button";
  addBtn.className = "btn primary";
  addBtn.textContent = "Add to library";
  const openDash = document.createElement("button");
  openDash.type = "button";
  openDash.className = "btn secondary";
  openDash.textContent = "Open dashboard";
  row.appendChild(addBtn);
  if (manualOnly) {
    requestSupportBtn = document.createElement("button");
    requestSupportBtn.type = "button";
    requestSupportBtn.className = "btn secondary";
    requestSupportBtn.textContent = "Request source support";
    row.appendChild(requestSupportBtn);
  } else {
    row.appendChild(openDash);
  }
  host.appendChild(row);

  addBtn.addEventListener("click", async () => {
    addBtn.disabled = true;
    const payload = {
      source_url: shaped.source_url || lastTabUrl || "",
      source_name: shaped.source_name || "",
      source_domain: shaped.source_domain || "",
      support_level: shaped.support_level || "manual_only",
      title: shaped.title || "",
      canonical_title: shaped.canonical_title || "",
      description: shaped.description || "",
      cover_url: shaped.cover_url || "",
      latest_chapter: shaped.latest_chapter || "",
      current_chapter: shaped.current_chapter || "",
      chapter_count: shaped.chapter_count || "",
      chapters: Array.isArray(shaped.chapters) ? shaped.chapters : [],
      warnings: Array.isArray(shaped.warnings) ? shaped.warnings : [],
      detection_source: shaped.detection_source || (extensionAssisted ? "extension" : "backend"),
      confidence: shaped.confidence ?? "",
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
        openAppBtn.type = "button";
        openAppBtn.className = "btn secondary";
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
    dash.type = "button";
    dash.className = "btn secondary";
    dash.textContent = "Open dashboard";
    const lib = document.createElement("button");
    lib.type = "button";
    lib.className = "btn secondary";
    lib.textContent = "View library";
    row.appendChild(dash);
    row.appendChild(lib);
    const openLibrary = () => chrome.tabs.create({ url: `${apiBase}/app` });
    dash.addEventListener("click", () => chrome.tabs.create({ url: `${apiBase}/app` }));
    lib.addEventListener("click", openLibrary);
  });

  if (!manualOnly) {
    openDash.addEventListener("click", () => chrome.tabs.create({ url: `${apiBase}/app` }));
  }
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
  $("resolverShell")?.classList.remove("hidden");
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
    if (forceBtn && forceBtn.dataset.bound !== "1") {
      forceBtn.dataset.bound = "1";
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

  if (trackBtn && trackBtn.dataset.bound !== "1") {
    trackBtn.dataset.bound = "1";
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
  }

  if (markReadBtn && markReadBtn.dataset.bound !== "1") {
    markReadBtn.dataset.bound = "1";
    markReadBtn.addEventListener("click", async () => {
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
  }

  bindFooter();
}

function bindFooter() {
  $("openOptions")?.addEventListener("click", openOptionsPage);
  $("openOptionsFooter")?.addEventListener("click", openOptionsPage);
  $("openDashboard")?.addEventListener("click", async () => {
    const settingsRes = await sendMessage({ type: "GET_SETTINGS" });
    const base = (settingsRes?.data?.apiBase || DEFAULT_API_BASE).replace(/\/$/, "");
    chrome.tabs.create({ url: `${base}/app` });
  });
}

init();
