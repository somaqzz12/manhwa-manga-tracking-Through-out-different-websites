function normalizeSeriesUrl(url, options = {}) {
  try {
    const u = new URL(url);
    u.hash = "";
    const parts = u.pathname.split("/").filter(Boolean);
    // Heuristic: drop obvious chapter-like trailing segment.
    if (parts.length > 1) {
      const last = parts[parts.length - 1];
      const prev = parts[parts.length - 2];
      const lastLooksChapter = /^(?:c\d+(?:\.\d+)?|chapter[-_\s]?\d+(?:\.\d+)?|ch[-_\s]?\d+(?:\.\d+)?|episode[-_\s]?\d+(?:\.\d+)?|ep[-_\s]?\d+(?:\.\d+)?)$/i.test(
        last
      );
      const splitLooksChapter = /^(?:chapter|ch|episode|ep)$/i.test(prev) && /^\d+(?:\.\d+)?$/i.test(last);
      if (lastLooksChapter || splitLooksChapter) {
        parts.pop();
        if (splitLooksChapter) parts.pop();
      }
    }
    // Reader pages that encode chapter as trailing "-<num>" in series slug.
    if (parts.length && options.dropTrailingSlugNumber) {
      const last = parts[parts.length - 1];
      parts[parts.length - 1] = last.replace(/([-_])\d+(?:\.\d+)?$/i, "");
      if (!parts[parts.length - 1]) {
        parts.pop();
      }
    }
    u.pathname = "/" + parts.join("/");
    return u.toString().replace(/\/$/, "");
  } catch {
    return url;
  }
}

const SUPPORTED_HOST_HINTS = [
  "asura",
  "reaper",
  "flame",
  "scan",
  "toon",
  "manga",
  "manhwa",
  "manhua",
  "webtoon",
  "bato",
  "comick",
  "mangadex",
  "manganato",
];

function slugify(text) {
  return (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function parseChapterFromText(text) {
  const m = (text || "").match(/(?:chapter|ch\.?|episode|ep\.?)\s*[:#-]?\s*(\d+(?:\.\d+)?)/i);
  return m ? Number(m[1]) : null;
}

function parseChapterFromUrl(url) {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    if (!parts.length) return null;

    if (parts.length >= 2 && /^(chapter|ch|episode|ep)$/i.test(parts[parts.length - 2])) {
      const n = Number(parts[parts.length - 1]);
      return Number.isFinite(n) ? n : null;
    }

    const tail = parts[parts.length - 1];
    const tailMatch = tail.match(/^(?:c|chapter|ch|episode|ep)[-_ ]?(\d+(?:\.\d+)?)$/i);
    if (tailMatch) return Number(tailMatch[1]);

    const m = u.pathname.match(/(?:chapter|ch|episode|ep)[^0-9]{0,3}(\d+(?:\.\d+)?)/i);
    return m ? Number(m[1]) : null;
  } catch {
    return null;
  }
}

function pathHasChapterSignal(path) {
  return (
    /\/c\d+(?:\.\d+)?(?:\/|$)/i.test(path) ||
    /\/(?:chapter|ch|episode|ep)\/\d+(?:\.\d+)?(?:\/|$)/i.test(path) ||
    /\/(?:chapter|ch|episode|ep)[^/]*\d+(?:\.\d+)?(?:\/|$)/i.test(path)
  );
}

function pageLooksLikeReader() {
  const imgs = document.querySelectorAll("img");
  let tallImageCount = 0;
  for (const img of imgs) {
    const h = img.naturalHeight || img.height || 0;
    const w = img.naturalWidth || img.width || 0;
    if (h >= 900 && w >= 500) tallImageCount += 1;
    if (tallImageCount >= 3) return true;
  }
  return false;
}

function pageHasReaderControls() {
  const bodyText = (document.body?.innerText || "").toLowerCase();
  if (bodyText.includes("select chapter")) return true;

  // Avoid global "prev/next" checks; they are common on unrelated pages.
  const containers = document.querySelectorAll("nav, .chapter-nav, .reader-nav, .pagination, .controls");
  for (const container of containers) {
    const txt = (container.textContent || "").toLowerCase();
    if (txt.includes("prev") && txt.includes("next")) return true;
  }
  return false;
}

function pathLooksLikeSeriesChapterSlug(path) {
  const clean = (path || "").toLowerCase().replace(/\/+$/, "");
  const parts = clean.split("/").filter(Boolean);
  if (!parts.length) return false;
  const tail = parts[parts.length - 1];
  // Covers patterns like /solo-bug-player-2 where chapter number is a trailing slug token.
  return /[a-z][a-z0-9-]*-\d+(?:\.\d+)?$/i.test(tail);
}

function isLikelyListingPage(path, bodyText) {
  const p = (path || "").toLowerCase().replace(/\/+$/, "") || "/";
  if (p === "/" || p === "/home") return true;
  if (/\/(comics|comic|browse|latest|latest-updates|updates|genres|genre|az-list|list|search|bookmark|bookmarks)$/.test(p)) {
    return true;
  }
  const t = (bodyText || "").toLowerCase();
  const listingHints = [
    "latest updates",
    "popular",
    "bookmark",
    "bookmarks",
    "genres",
    "manga list",
    "az list",
  ];
  let hitCount = 0;
  for (const hint of listingHints) {
    if (t.includes(hint)) hitCount += 1;
  }
  const chapterMentions = (t.match(/chapter\s+\d+/g) || []).length;
  return hitCount >= 2 || chapterMentions >= 8;
}

function isBlockedHost(host) {
  const blocked = [
    "google.", "youtube.", "github.", "stackoverflow.", "reddit.", "x.com", "twitter.", "facebook.", "instagram.",
    "linkedin.", "wikipedia.", "amazon.", "microsoft.", "apple.", "netflix.", "twitch.", "discord.", "chat.openai.com",
  ];
  return blocked.some((d) => host.includes(d));
}

function cleanSeriesTitle(rawTitle) {
  let t = (rawTitle || "").trim();
  t = t.replace(/\s*[-|:]\s*(asura|reaper|flame|scan[s]?|scans).*$/i, "");
  t = t.replace(/\b(read online|raw|official)\b/gi, "");
  t = t.replace(/\b(chapter|ch\.?|episode|ep\.?)\s*[:#-]?\s*\d+(\.\d+)?(\s*\([^)]*\))?/gi, "");
  t = t.replace(/\s+/g, " ").trim();
  return t || rawTitle || "Untitled series";
}

function deriveSeriesSlug(seriesUrl, fallbackTitle) {
  try {
    const u = new URL(seriesUrl);
    const parts = u.pathname.split("/").filter(Boolean);
    if (!parts.length) return slugify(cleanSeriesTitle(fallbackTitle));
    const tail = parts[parts.length - 1];
    // Prefer stable URL slug over page title to avoid duplicate keys.
    const stable = tail.replace(/[-_](?:\d+(?:\.\d+)?)$/g, "").trim();
    return slugify(stable || cleanSeriesTitle(fallbackTitle));
  } catch {
    return slugify(cleanSeriesTitle(fallbackTitle));
  }
}

function buildSeriesKey(seriesUrl, title) {
  try {
    const u = new URL(seriesUrl);
    const host = u.hostname.replace(/^www\./, "").toLowerCase();
    const seriesSlug = deriveSeriesSlug(seriesUrl, title);
    return `${host}::${seriesSlug}`;
  } catch {
    return `unknown::${slugify(cleanSeriesTitle(title))}`;
  }
}

function looksLikeMangaSite(url, title) {
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    const path = u.pathname.toLowerCase();
    const t = (title || "").toLowerCase();

    if (isBlockedHost(host)) {
      return false;
    }

    const hostHasHint = SUPPORTED_HOST_HINTS.some((hint) => host.includes(hint));
    const pathHasChapter = pathHasChapterSignal(path);
    const pathHasSlugChapter = pathLooksLikeSeriesChapterSlug(path);
    const titleHasChapter = /(?:chapter|ch\.?|episode|ep\.?)\s*[:#-]?\s*\d+/i.test(t);
    const bodyText = document.body?.innerText || "";
    const readerLikeDom = pageLooksLikeReader();
    const readerControls = pageHasReaderControls();
    const listingPage = isLikelyListingPage(path, bodyText);

    if (listingPage && !pathHasChapter && !pathHasSlugChapter && !titleHasChapter && !readerLikeDom && !readerControls) {
      return false;
    }

    // Strong signal: chapter-like URL plus chapter-like title.
    if (pathHasChapter && titleHasChapter) return true;
    // Reader-like page plus chapter-like URL.
    if (pathHasChapter && readerLikeDom) return true;
    // Some sites use series-slug-with-number chapter paths instead of /chapter/NN.
    if (pathHasSlugChapter && hostHasHint && (readerLikeDom || readerControls || titleHasChapter)) return true;
    // Reader controls are a fallback only with explicit chapter signal.
    if (hostHasHint && readerControls && (pathHasChapter || pathHasSlugChapter || titleHasChapter)) return true;
    // Strong chapter signal with host hints.
    if (hostHasHint && (pathHasChapter || titleHasChapter) && (readerLikeDom || readerControls)) return true;
    return false;
  } catch {
    return false;
  }
}

function detectPageData() {
  const url = window.location.href;
  const title = document.title || "Untitled series";
  const u = new URL(url);
  const path = u.pathname.toLowerCase();
  const pathHasSlugChapter = pathLooksLikeSeriesChapterSlug(path);
  const readerControls = pageHasReaderControls();
  if (!looksLikeMangaSite(url, title)) {
    return null;
  }
  const cleanedTitle = cleanSeriesTitle(title);
  const seriesUrl = normalizeSeriesUrl(url, { dropTrailingSlugNumber: pathHasSlugChapter && readerControls });
  const seriesKey = buildSeriesKey(seriesUrl, cleanedTitle);
  const chapterNum = parseChapterFromText(title) ?? parseChapterFromUrl(url);
  return {
    title: cleanedTitle,
    seriesUrl,
    seriesKey,
    chapterUrl: url,
    chapterLabel: title,
    chapterNum,
  };
}

async function sendMessage(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (response) => resolve(response));
  });
}

function getTrackDataFromPage() {
  const data = detectPageData();
  if (!data || !data.seriesUrl || data.seriesUrl.startsWith("chrome://")) return null;
  return data;
}

function showTrackPrompt(data) {
  return new Promise((resolve) => {
    const existing = document.getElementById("manga-tracker-track-modal");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "manga-tracker-track-modal";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(2, 6, 23, 0.65)";
    overlay.style.backdropFilter = "blur(4px)";
    overlay.style.zIndex = "2147483647";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.padding = "16px";

    const card = document.createElement("div");
    card.style.width = "min(520px, 96vw)";
    card.style.background = "linear-gradient(180deg, #0b1228 0%, #0a1020 100%)";
    card.style.border = "1px solid rgba(148, 163, 184, 0.25)";
    card.style.borderRadius = "16px";
    card.style.boxShadow = "0 24px 60px rgba(2, 6, 23, 0.6)";
    card.style.padding = "18px";
    card.style.color = "#e5e7eb";
    card.style.fontFamily = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif";

    const title = document.createElement("div");
    title.textContent = "Track this series?";
    title.style.fontSize = "22px";
    title.style.fontWeight = "700";
    title.style.marginBottom = "8px";

    const subtitle = document.createElement("div");
    subtitle.textContent = data.title || "Untitled series";
    subtitle.style.fontSize = "18px";
    subtitle.style.fontWeight = "600";
    subtitle.style.color = "#93c5fd";
    subtitle.style.marginBottom = "10px";

    const seriesUrl = document.createElement("div");
    seriesUrl.textContent = data.seriesUrl;
    seriesUrl.style.fontSize = "12px";
    seriesUrl.style.opacity = "0.8";
    seriesUrl.style.wordBreak = "break-all";
    seriesUrl.style.marginBottom = "16px";

    const btnRow = document.createElement("div");
    btnRow.style.display = "flex";
    btnRow.style.gap = "10px";
    btnRow.style.justifyContent = "flex-end";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Not now";
    cancelBtn.style.border = "1px solid rgba(148, 163, 184, 0.4)";
    cancelBtn.style.background = "#233149";
    cancelBtn.style.color = "#e2e8f0";
    cancelBtn.style.padding = "10px 14px";
    cancelBtn.style.borderRadius = "10px";
    cancelBtn.style.cursor = "pointer";

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.textContent = "Track";
    okBtn.style.border = "none";
    okBtn.style.background = "linear-gradient(180deg, #3b82f6 0%, #2563eb 100%)";
    okBtn.style.color = "white";
    okBtn.style.padding = "10px 16px";
    okBtn.style.borderRadius = "10px";
    okBtn.style.fontWeight = "700";
    okBtn.style.cursor = "pointer";

    const close = (decision) => {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      resolve(decision);
    };

    cancelBtn.addEventListener("click", () => close(false));
    okBtn.addEventListener("click", () => close(true));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(false);
    });
    const onKeyDown = (e) => {
      if (e.key === "Escape") close(false);
    };
    document.addEventListener("keydown", onKeyDown);

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(okBtn);
    card.appendChild(title);
    card.appendChild(subtitle);
    card.appendChild(seriesUrl);
    card.appendChild(btnRow);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
  });
}

async function saveTrackData(data) {
  if (!data) return { ok: false, error: "No trackable data on this page." };
  const promptKey = `mangaTrackerPrompt:${data.seriesUrl}:${data.chapterUrl}`;
  if (sessionStorage.getItem(promptKey) === "1") return { ok: true, skipped: true };

  let seriesPromptStableKey = data.seriesKey || data.seriesUrl;
  try {
    seriesPromptStableKey = `${new URL(data.seriesUrl).hostname}:${data.seriesUrl}`;
  } catch {}
  const seenSeriesPromptKey = `mangaTrackerSeriesPrompted:${seriesPromptStableKey}`;
  const snoozePromptKey = `mangaTrackerSeriesPromptSnoozed:${seriesPromptStableKey}`;
  const snoozedUntil = Number(localStorage.getItem(snoozePromptKey) || "0");
  if (Date.now() < snoozedUntil) {
    sessionStorage.setItem(promptKey, "1");
    return { ok: true, skipped: true };
  }
  const seenSeriesPrompt =
    sessionStorage.getItem(seenSeriesPromptKey) === "1" ||
    localStorage.getItem(seenSeriesPromptKey) === "1";
  if (!seenSeriesPrompt) {
    const shouldTrack = await showTrackPrompt(data);
    if (!shouldTrack) {
      // Cooldown cancel prompts so users are not interrupted on every chapter.
      localStorage.setItem(snoozePromptKey, String(Date.now() + 24 * 60 * 60 * 1000));
      sessionStorage.setItem(promptKey, "1");
      return { ok: false, error: "User skipped tracking." };
    }
    sessionStorage.setItem(seenSeriesPromptKey, "1");
    localStorage.setItem(seenSeriesPromptKey, "1");
  }
  sessionStorage.setItem(promptKey, "1");

  const ensure = await sendMessage({
    type: "ENSURE_SERIES",
    payload: { title: data.title, url: data.seriesUrl, series_key: data.seriesKey },
  });
  if (!ensure?.ok) return { ok: false, error: ensure?.error || "Series ensure failed." };

  const progressRes = await sendMessage({
    type: "SAVE_PROGRESS",
    payload: {
      series_url: data.seriesUrl,
      series_key: data.seriesKey,
      chapter_url: data.chapterUrl,
      chapter_label: data.chapterLabel,
      chapter_num: data.chapterNum,
    },
  });
  if (!progressRes?.ok) return { ok: false, error: progressRes?.error || "Progress save failed." };
  return { ok: true, data };
}

async function maybeTrack() {
  const data = getTrackDataFromPage();
  if (!data) return;
  await saveTrackData(data);
}

let __lastUrl = "";
let __lastAttemptAt = 0;
let __trackInFlight = false;
async function maybeTrackOnRouteChange() {
  if (__trackInFlight) return;
  const now = Date.now();
  const href = window.location.href;
  if (href === __lastUrl && now - __lastAttemptAt < 1500) return;
  __lastUrl = href;
  __lastAttemptAt = now;
  __trackInFlight = true;
  try {
    await maybeTrack();
  } finally {
    __trackInFlight = false;
  }
}

if (document.readyState === "complete" || document.readyState === "interactive") {
  maybeTrackOnRouteChange();
} else {
  window.addEventListener("DOMContentLoaded", maybeTrackOnRouteChange, { once: true });
}

// Support SPA chapter navigation where URL changes without full page reload.
setInterval(() => {
  maybeTrackOnRouteChange();
}, 1200);

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg?.type === "GET_PAGE_TRACK_DATA") {
      sendResponse({ ok: true, data: getTrackDataFromPage() });
      return;
    }
    if (msg?.type === "TRACK_NOW") {
      const result = await saveTrackData(getTrackDataFromPage());
      sendResponse(result);
      return;
    }
    sendResponse({ ok: false, error: "Unknown content message" });
  })();
  return true;
});
