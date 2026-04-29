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
  "mangakakalot",
  "mangapark",
  "mangabuddy",
  "mangaowl",
  "mangahere",
  "mangafox",
  "mangafire",
  "kissmanga",
  "manga4life",
  "mangasee",
  "lhtranslation",
  "cosmicscans",
  "luminousscans",
  "anigliscans",
  "leviatanscans",
  "drakescans",
  "isekaiscan",
  "rizzcomic",
  "rawkuma",
  "tcb",
  "zinmanga",
  "earlymanga",
];

// Per-host extractors that override the generic title/chapter heuristics. Each
// matcher returns null when the page does not look like a chapter page on that
// host, falling through to the generic detection in detectPageData.
const HOST_EXTRACTORS = [
  {
    match: (host) => host.endsWith("mangadex.org"),
    extract: () => extractMangaDexFromDom(),
  },
  {
    match: (host) => host.endsWith("webtoons.com"),
    extract: () => extractWebtoons(),
  },
  {
    match: (host) => host.includes("bato.to") || host.endsWith("batocomic.com"),
    extract: () => extractBato(),
  },
  {
    match: (host) => host.includes("asura") || host.includes("rizzcomic") || host.includes("flamescans") || host.includes("reaper"),
    extract: () => extractAsuraFamily(),
  },
];

function extractMangaDexFromDom() {
  // MangaDex renders chapter pages at /chapter/<uuid>. We only confirm the URL
  // shape here; the heavy lifting (fetching series title via the REST API)
  // happens later in detectPageData via background fetch.
  try {
    const u = new URL(window.location.href);
    const uuid = (u.pathname.match(/\/chapter\/([0-9a-f-]{8,})/i) || [])[1];
    if (!uuid) return null;
    return { mangadexChapterUuid: uuid };
  } catch {
    return null;
  }
}

function extractWebtoons() {
  // Webtoons pages put the series title in og:title and chapter number in the
  // URL: /viewer?title_no=...&episode_no=NN
  const ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute("content") || "";
  let chapterNum = null;
  try {
    const u = new URL(window.location.href);
    const ep = Number(u.searchParams.get("episode_no"));
    if (Number.isFinite(ep)) chapterNum = ep;
  } catch {}
  if (!ogTitle && chapterNum == null) return null;
  return {
    title: ogTitle.replace(/\|.*$/, "").trim() || null,
    chapterNum,
  };
}

function extractBato() {
  // Bato.to chapter pages expose the series title in the breadcrumb header.
  const seriesTitle = document.querySelector(".nav-title a")?.textContent
    || document.querySelector("h3 a[href*='/series/']")?.textContent
    || null;
  const chapterTitle = document.querySelector("h6")?.textContent
    || document.querySelector(".nav-title")?.textContent
    || null;
  let chapterNum = null;
  if (chapterTitle) chapterNum = parseChapterFromText(chapterTitle);
  if (chapterNum == null) chapterNum = parseChapterFromUrl(window.location.href);
  if (!seriesTitle && chapterNum == null) return null;
  return { title: seriesTitle?.trim() || null, chapterNum };
}

function extractAsuraFamily() {
  // AsuraScans / RizzComic / Flame / Reaper share a common Madara-style theme
  // where the series title sits in .breadcrumb a or .ts-breadcrumb a.
  const breadcrumb = document.querySelector(".allc a, .ts-breadcrumb a:nth-child(2), .breadcrumb a:nth-child(2)");
  const seriesTitle = breadcrumb?.textContent?.trim() || null;
  let chapterNum = parseChapterFromUrl(window.location.href);
  if (chapterNum == null) {
    const heading = document.querySelector("h1, .entry-title, .chapter-title")?.textContent;
    if (heading) chapterNum = parseChapterFromText(heading);
  }
  if (!seriesTitle && chapterNum == null) return null;
  return { title: seriesTitle, chapterNum };
}

function runHostExtractor(host) {
  for (const entry of HOST_EXTRACTORS) {
    try {
      if (entry.match(host)) {
        const result = entry.extract();
        if (result) return result;
      }
    } catch {}
  }
  return null;
}

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

function countLargeImages() {
  // Cheap, capped scan to act as a negative signal: chapter pages typically
  // have many large images, while series-listing pages and search results have
  // few or none.
  const imgs = document.querySelectorAll("img");
  let large = 0;
  let scanned = 0;
  for (const img of imgs) {
    scanned += 1;
    const w = img.naturalWidth || img.width || 0;
    if (w >= 600) large += 1;
    if (scanned >= 200) break;
  }
  return large;
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

    // Negative signal: chapter-looking URL on a host hint, but the page has
    // essentially no large images. Common on series detail pages that mention
    // "Chapter N" in a recommendations list. We still allow the strongest
    // combo (chapter URL + chapter title + reader DOM) through, but we
    // downgrade weaker single-signal matches.
    const largeImages = countLargeImages();
    const veryFewImages = largeImages < 2;

    // Strong signal: chapter-like URL plus chapter-like title.
    if (pathHasChapter && titleHasChapter && !veryFewImages) return true;
    // Reader-like page plus chapter-like URL.
    if (pathHasChapter && readerLikeDom) return true;
    // Some sites use series-slug-with-number chapter paths instead of /chapter/NN.
    if (pathHasSlugChapter && hostHasHint && (readerLikeDom || readerControls || titleHasChapter) && !veryFewImages) return true;
    // Reader controls are a fallback only with explicit chapter signal.
    if (hostHasHint && readerControls && (pathHasChapter || pathHasSlugChapter || titleHasChapter) && !veryFewImages) return true;
    // Strong chapter signal with host hints.
    if (hostHasHint && (pathHasChapter || titleHasChapter) && (readerLikeDom || readerControls)) return true;
    return false;
  } catch {
    return false;
  }
}

async function detectPageData() {
  const url = window.location.href;
  const title = document.title || "Untitled series";
  const u = new URL(url);
  const host = u.hostname.replace(/^www\./, "").toLowerCase();
  const path = u.pathname.toLowerCase();
  const pathHasSlugChapter = pathLooksLikeSeriesChapterSlug(path);
  const readerControls = pageHasReaderControls();

  // MangaDex chapter pages are React-rendered and unstable to scrape, so we
  // detour through the public REST API for a clean series title and chapter
  // number. Fail soft to the generic flow if the API is unreachable.
  if (host.endsWith("mangadex.org")) {
    const mangadex = await detectMangaDexFromApi(u);
    if (mangadex) return mangadex;
  }

  if (!looksLikeMangaSite(url, title)) {
    return null;
  }

  const hostExtractor = runHostExtractor(host);
  const overrideTitle = hostExtractor?.title || null;
  const overrideChapter = hostExtractor?.chapterNum;

  const cleanedTitle = cleanSeriesTitle(overrideTitle || title);
  const seriesUrl = normalizeSeriesUrl(url, { dropTrailingSlugNumber: pathHasSlugChapter && readerControls });
  const seriesKey = buildSeriesKey(seriesUrl, cleanedTitle);
  const chapterNum =
    overrideChapter != null
      ? Number(overrideChapter)
      : parseChapterFromText(title) ?? parseChapterFromUrl(url);
  return {
    title: cleanedTitle,
    seriesUrl,
    seriesKey,
    chapterUrl: url,
    chapterLabel: title,
    chapterNum,
  };
}

async function detectMangaDexFromApi(parsedUrl) {
  const uuidMatch = parsedUrl.pathname.match(/\/chapter\/([0-9a-f-]{8,})/i);
  if (!uuidMatch) return null;
  const uuid = uuidMatch[1];
  let chapterRes;
  try {
    chapterRes = await sendMessage({ type: "MANGADEX_FETCH", payload: { uuid } });
  } catch {
    return null;
  }
  const data = chapterRes?.data;
  if (!chapterRes?.ok || !data) return null;
  const titles = data?.attributes?.title || {};
  const altTitles = data?.attributes?.altTitles || [];
  const seriesTitle =
    titles.en ||
    titles["ja-ro"] ||
    Object.values(titles)[0] ||
    altTitles.find((t) => t?.en)?.en ||
    "Untitled series";
  const mangaId = data?.relationships?.find?.((r) => r.type === "manga")?.id;
  const seriesUrl = mangaId ? `https://mangadex.org/title/${mangaId}` : `https://mangadex.org${parsedUrl.pathname}`;
  const chapterAttr = data?.chapterAttributes?.chapter ?? data?.chapter;
  const chapterNumRaw = chapterAttr != null ? Number(chapterAttr) : null;
  const seriesKey = buildSeriesKey(seriesUrl, seriesTitle);
  return {
    title: cleanSeriesTitle(seriesTitle),
    seriesUrl,
    seriesKey,
    chapterUrl: parsedUrl.toString(),
    chapterLabel: chapterAttr != null ? `Chapter ${chapterAttr}` : document.title || "Chapter",
    chapterNum: Number.isFinite(chapterNumRaw) ? chapterNumRaw : null,
  };
}

async function sendMessage(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (response) => resolve(response));
  });
}

async function getTrackDataFromPage() {
  const data = await detectPageData();
  if (!data || !data.seriesUrl || data.seriesUrl.startsWith("chrome://")) return null;
  return data;
}

function showTrackPrompt(data) {
  return new Promise((resolve) => {
    const existing = document.getElementById("zero-hour-track-modal");
    if (existing) existing.remove();

    // Host element lives in the page; everything visible lives inside its closed
    // Shadow DOM so site stylesheets cannot reach the modal markup.
    const host = document.createElement("div");
    host.id = "zero-hour-track-modal";
    host.style.all = "initial";
    host.style.position = "fixed";
    host.style.inset = "0";
    host.style.zIndex = "2147483647";
    host.style.pointerEvents = "auto";

    const root = host.attachShadow({ mode: "closed" });

    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      .overlay {
        position: fixed;
        inset: 0;
        background: rgba(2, 6, 23, 0.65);
        backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
        font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        color: #e5e7eb;
      }
      .card {
        width: min(520px, 96vw);
        background: linear-gradient(180deg, #0b1228 0%, #0a1020 100%);
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 16px;
        box-shadow: 0 24px 60px rgba(2, 6, 23, 0.6);
        padding: 18px;
        box-sizing: border-box;
      }
      .title { font-size: 22px; font-weight: 700; margin: 0 0 8px; }
      .subtitle { font-size: 18px; font-weight: 600; color: #93c5fd; margin: 0 0 10px; }
      .series-url { font-size: 12px; opacity: 0.8; word-break: break-all; margin: 0 0 16px; }
      .btn-row { display: flex; gap: 10px; justify-content: flex-end; }
      button {
        font: inherit;
        border-radius: 10px;
        cursor: pointer;
      }
      .cancel {
        border: 1px solid rgba(148, 163, 184, 0.4);
        background: #233149;
        color: #e2e8f0;
        padding: 10px 14px;
      }
      .ok {
        border: none;
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
        color: #ffffff;
        padding: 10px 16px;
        font-weight: 700;
      }
    `;

    const overlay = document.createElement("div");
    overlay.className = "overlay";

    const card = document.createElement("div");
    card.className = "card";

    const title = document.createElement("div");
    title.className = "title";
    title.textContent = "Track this series?";

    const subtitle = document.createElement("div");
    subtitle.className = "subtitle";
    subtitle.textContent = data.title || "Untitled series";

    const seriesUrl = document.createElement("div");
    seriesUrl.className = "series-url";
    seriesUrl.textContent = data.seriesUrl;

    const btnRow = document.createElement("div");
    btnRow.className = "btn-row";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "cancel";
    cancelBtn.textContent = "Not now";

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "ok";
    okBtn.textContent = "Track";

    const close = (decision) => {
      document.removeEventListener("keydown", onKeyDown);
      host.remove();
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
    root.appendChild(style);
    root.appendChild(overlay);
    document.body.appendChild(host);
  });
}

const DEFAULT_COOLDOWN_HOURS = 24;
let __cachedSettings = null;

async function getSettings() {
  if (__cachedSettings) return __cachedSettings;
  try {
    const stored = await chrome.storage.local.get(["autoTrack", "cooldownHours"]);
    __cachedSettings = {
      autoTrack: Boolean(stored.autoTrack),
      cooldownHours: Number.isFinite(stored.cooldownHours)
        ? stored.cooldownHours
        : DEFAULT_COOLDOWN_HOURS,
    };
  } catch {
    __cachedSettings = { autoTrack: false, cooldownHours: DEFAULT_COOLDOWN_HOURS };
  }
  return __cachedSettings;
}

if (chrome.storage?.onChanged) {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if ("autoTrack" in changes || "cooldownHours" in changes) {
      __cachedSettings = null;
    }
  });
}

async function saveTrackData(data) {
  if (!data) return { ok: false, error: "No trackable data on this page." };
  const promptKey = `mangaTrackerPrompt:${data.seriesUrl}:${data.chapterUrl}`;
  if (sessionStorage.getItem(promptKey) === "1") return { ok: true, skipped: true };

  const settings = await getSettings();

  // Snooze and "already seen" state are keyed by the stable seriesKey only.
  // Falling back to the full URL fragments these records across query strings,
  // trailing slashes, and chapter URLs, so we skip persistent snooze writes
  // entirely when no stable key is available.
  const stableKey = data.seriesKey || null;
  const seenSeriesPromptKey = stableKey ? `mangaTrackerSeriesPrompted:${stableKey}` : null;
  const snoozePromptKey = stableKey ? `mangaTrackerSeriesPromptSnoozed:${stableKey}` : null;

  if (settings.autoTrack) {
    // Silent auto-track skips both the modal and the snooze gate; the
    // sessionStorage promptKey above already prevents repeated writes for the
    // same chapter URL within a single tab session.
    sessionStorage.setItem(promptKey, "1");
    if (seenSeriesPromptKey) {
      sessionStorage.setItem(seenSeriesPromptKey, "1");
      localStorage.setItem(seenSeriesPromptKey, "1");
    }
  } else {
    if (snoozePromptKey) {
      const snoozedUntil = Number(localStorage.getItem(snoozePromptKey) || "0");
      if (Date.now() < snoozedUntil) {
        sessionStorage.setItem(promptKey, "1");
        return { ok: true, skipped: true };
      }
    }
    const seenSeriesPrompt =
      seenSeriesPromptKey != null &&
      (sessionStorage.getItem(seenSeriesPromptKey) === "1" ||
        localStorage.getItem(seenSeriesPromptKey) === "1");
    if (!seenSeriesPrompt) {
      const shouldTrack = await showTrackPrompt(data);
      if (!shouldTrack) {
        if (snoozePromptKey) {
          const cooldownMs = Math.max(0, settings.cooldownHours) * 60 * 60 * 1000;
          if (cooldownMs > 0) {
            localStorage.setItem(snoozePromptKey, String(Date.now() + cooldownMs));
          }
        }
        sessionStorage.setItem(promptKey, "1");
        return { ok: false, error: "User skipped tracking." };
      }
      if (seenSeriesPromptKey) {
        sessionStorage.setItem(seenSeriesPromptKey, "1");
        localStorage.setItem(seenSeriesPromptKey, "1");
      }
    }
    sessionStorage.setItem(promptKey, "1");
  }

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
  const data = await getTrackDataFromPage();
  if (!data) return;
  await saveTrackData(data);
}

let __lastUrl = "";
let __lastTitle = "";
let __lastAttemptAt = 0;
let __trackInFlight = false;
async function maybeTrackOnRouteChange() {
  if (__trackInFlight) return;
  const now = Date.now();
  const href = window.location.href;
  const titleNow = document.title || "";
  // Re-check when either the URL or the page title changed; the title gate
  // catches content-swap SPAs that mutate the DOM without changing the URL.
  const sameRoute = href === __lastUrl && titleNow === __lastTitle;
  if (sameRoute && now - __lastAttemptAt < 1500) return;
  __lastUrl = href;
  __lastTitle = titleNow;
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

// SPA navigation poll. Slowed from 1.2s to 2.5s and paused while the tab is
// hidden, since chapter pages can sit in background tabs for hours.
const SPA_POLL_INTERVAL_MS = 2500;
setInterval(() => {
  if (document.hidden) return;
  maybeTrackOnRouteChange();
}, SPA_POLL_INTERVAL_MS);

// When the tab becomes visible again, force a fresh check immediately so the
// user does not have to wait up to 2.5s for the next poll tick.
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) maybeTrackOnRouteChange();
});

// Some readers swap chapter content via fetch + innerHTML without changing the
// URL. A debounced MutationObserver picks up those transitions; the
// short-circuit in maybeTrackOnRouteChange keeps this cheap when nothing real
// has changed.
let __mutationDebounce = null;
const __mutationObserver = new MutationObserver(() => {
  if (document.hidden) return;
  if (__mutationDebounce) return;
  __mutationDebounce = setTimeout(() => {
    __mutationDebounce = null;
    maybeTrackOnRouteChange();
  }, 750);
});

function startMutationObserver() {
  if (!document.body) return;
  __mutationObserver.observe(document.body, { childList: true, subtree: true });
  if (document.head) {
    __mutationObserver.observe(document.head, { childList: true, subtree: true, characterData: true });
  }
}

if (document.body) {
  startMutationObserver();
} else {
  window.addEventListener("DOMContentLoaded", startMutationObserver, { once: true });
}

function clearPageSnoozeRecords() {
  let removed = 0;
  try {
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (
        key &&
        (key.startsWith("mangaTrackerSeriesPrompted:") ||
          key.startsWith("mangaTrackerSeriesPromptSnoozed:"))
      ) {
        keysToRemove.push(key);
      }
    }
    for (const key of keysToRemove) {
      localStorage.removeItem(key);
      removed += 1;
    }
  } catch {}
  try {
    const sessionKeys = [];
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith("mangaTrackerPrompt")) sessionKeys.push(key);
    }
    for (const key of sessionKeys) sessionStorage.removeItem(key);
  } catch {}
  return removed;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg?.type === "GET_PAGE_TRACK_DATA") {
      const data = await getTrackDataFromPage();
      sendResponse({ ok: true, data });
      return;
    }
    if (msg?.type === "TRACK_NOW") {
      const data = await getTrackDataFromPage();
      const result = await saveTrackData(data);
      sendResponse(result);
      return;
    }
    if (msg?.type === "CLEAR_PAGE_SNOOZES_CONTENT") {
      const removed = clearPageSnoozeRecords();
      sendResponse({ ok: true, removed });
      return;
    }
    sendResponse({ ok: false, error: "Unknown content message" });
  })();
  return true;
});
