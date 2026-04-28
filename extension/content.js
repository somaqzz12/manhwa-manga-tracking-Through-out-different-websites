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
  const selectChapterText = bodyText.includes("select chapter");
  const prevNextText = bodyText.includes(" prev ") && bodyText.includes(" next ");
  const navButtons = document.querySelectorAll("a, button");
  let prevNextLinks = 0;
  for (const node of navButtons) {
    const t = (node.textContent || "").trim().toLowerCase();
    if (t === "prev" || t === "next") {
      prevNextLinks += 1;
      if (prevNextLinks >= 2) return true;
    }
  }
  return selectChapterText || prevNextText;
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

    if (host.includes("youtube.com") || host.includes("google.com") || host.includes("github.com")) {
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
    // Reader controls are often a reliable fallback for chapter pages.
    if (hostHasHint && readerControls && (pathHasChapter || pathHasSlugChapter || titleHasChapter)) return true;
    // Host looks like manga site and strong chapter signal.
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

async function getDebugMode() {
  const settingsRes = await sendMessage({ type: "GET_SETTINGS" });
  return settingsRes?.ok ? !!settingsRes.data.debugMode : false;
}

async function reportDebug(event, details) {
  const debugMode = await getDebugMode();
  if (!debugMode) return;
  await sendMessage({
    type: "TRACK_DEBUG",
    payload: {
      event,
      details,
      at: new Date().toISOString(),
    },
  });
}

async function maybeTrack() {
  const settingsRes = await sendMessage({ type: "GET_SETTINGS" });
  const autoprompt = settingsRes?.ok ? settingsRes.data.autoprompt : true;
  const data = detectPageData();
  if (!data || !data.seriesUrl || data.seriesUrl.startsWith("chrome://")) {
    await reportDebug("skip-page", { reason: "unsupported-or-missing-data", url: window.location.href });
    return;
  }
  const promptKey = `mangaTrackerPrompt:${data.seriesUrl}:${data.chapterUrl}`;
  if (sessionStorage.getItem(promptKey) === "1") return;

  const knownKey = `mangaTrackerKnownSeries:${data.seriesKey}`;
  const knownSeries = localStorage.getItem(knownKey) === "1";

  if (autoprompt && !knownSeries) {
    const shouldAdd = window.confirm(
      `Track this series?\n\n${data.title}\n${data.seriesUrl}`
    );
    if (!shouldAdd) return;
  }
  sessionStorage.setItem(promptKey, "1");

  const ensure = await sendMessage({
    type: "ENSURE_SERIES",
    payload: { title: data.title, url: data.seriesUrl, series_key: data.seriesKey },
  });
  await reportDebug("ensure-series", {
    payload: { title: data.title, url: data.seriesUrl, series_key: data.seriesKey },
    response: ensure,
  });
  if (!ensure?.ok) return;
  localStorage.setItem(knownKey, "1");

  const progress = await sendMessage({
    type: "SAVE_PROGRESS",
    payload: {
      series_url: data.seriesUrl,
      series_key: data.seriesKey,
      chapter_url: data.chapterUrl,
      chapter_label: data.chapterLabel,
      chapter_num: data.chapterNum,
    },
  });
  await reportDebug("save-progress", {
    parsed: {
      normalized_series_url: data.seriesUrl,
      series_key: data.seriesKey,
      chapter_num: data.chapterNum,
      chapter_url: data.chapterUrl,
    },
    response: progress,
  });
}

if (document.readyState === "complete" || document.readyState === "interactive") {
  maybeTrack();
} else {
  window.addEventListener("DOMContentLoaded", maybeTrack, { once: true });
}
