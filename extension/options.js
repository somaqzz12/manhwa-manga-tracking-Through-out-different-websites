// `DEFAULT_API_BASE` comes from extension/config.js, loaded before this script in options.html.
const DEFAULT_COOLDOWN_HOURS = 24;

const $ = (id) => document.getElementById(id);

function setStatus(el, text, kind = "") {
  if (!el) return;
  el.textContent = text || "";
  el.className = `status ${kind}`.trim();
}

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

async function loadSettings() {
  const stored = await chrome.storage.local.get([
    "apiBase",
    "autoTrack",
    "cooldownHours",
  ]);
  $("apiBase").value = (stored.apiBase || DEFAULT_API_BASE).trim();
  $("autoTrack").checked = Boolean(stored.autoTrack);
  $("cooldownHours").value = Number.isFinite(stored.cooldownHours)
    ? stored.cooldownHours
    : DEFAULT_COOLDOWN_HOURS;
}

async function ensureBackendHostPermission(origin) {
  const origins = [`${origin}/*`];
  try {
    if (await chrome.permissions.contains({ origins })) {
      return { ok: true };
    }
    const granted = await chrome.permissions.request({ origins });
    return {
      ok: granted,
      error: granted ? null : "Chrome denied host access — API calls to this URL will fail.",
    };
  } catch (err) {
    return { ok: false, error: String(err?.message || err) };
  }
}

async function saveApiBase() {
  const raw = ($("apiBase").value || "").trim().replace(/\/$/, "");
  if (!raw) {
    setStatus($("apiStatus"), "Backend URL cannot be empty.", "error");
    return;
  }
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    setStatus($("apiStatus"), "Not a valid URL.", "error");
    return;
  }
  const perm = await ensureBackendHostPermission(parsed.origin);
  if (!perm.ok) {
    setStatus($("apiStatus"), perm.error || "Could not obtain host permission.", "error");
    return;
  }
  await chrome.storage.local.set({ apiBase: raw });
  $("apiBase").value = raw;
  setStatus($("apiStatus"), `Saved: ${raw}`, "ok");
}

async function testConnection() {
  const raw = ($("apiBase").value || "").trim().replace(/\/$/, "") || DEFAULT_API_BASE;
  setStatus($("apiStatus"), `Pinging ${raw}/healthz...`);
  try {
    const res = await fetch(`${raw}/healthz`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    });
    if (res.ok) {
      setStatus($("apiStatus"), `Connected (HTTP ${res.status}).`, "ok");
    } else {
      setStatus($("apiStatus"), `Backend responded with HTTP ${res.status}.`, "error");
    }
  } catch (err) {
    setStatus($("apiStatus"), `Could not reach backend: ${err.message || err}`, "error");
  }
}

async function saveBehavior() {
  const autoTrack = $("autoTrack").checked;
  const rawHours = Number($("cooldownHours").value);
  const cooldownHours = Number.isFinite(rawHours) && rawHours >= 0 ? rawHours : DEFAULT_COOLDOWN_HOURS;
  await chrome.storage.local.set({ autoTrack, cooldownHours });
  $("cooldownHours").value = cooldownHours;
  setStatus(
    $("behaviorStatus"),
    `Saved. Auto-track ${autoTrack ? "on" : "off"}, cooldown ${cooldownHours}h.`,
    "ok"
  );
}

async function clearLocalData() {
  if (!confirm("Clear all local extension data? Settings, debug log, and snooze records will be wiped.")) return;
  await chrome.storage.local.clear();
  await chrome.storage.session?.clear?.().catch(() => {});
  // localStorage snooze keys live in each page's origin and cannot be wiped
  // from here; the background broadcasts a request to open tabs to do it for us.
  await sendMessage({ type: "CLEAR_PAGE_SNOOZES" });
  await loadSettings();
  await renderDebugLog();
  setStatus(
    $("dataStatus"),
    "Local extension data cleared. Page-level snooze records were also requested to be cleared from open tabs.",
    "ok"
  );
}

function formatTimestamp(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}

async function renderDebugLog() {
  const stored = await chrome.storage.local.get(["debugEvents"]);
  const events = Array.isArray(stored.debugEvents) ? stored.debugEvents.slice().reverse() : [];
  const root = $("debugLog");
  root.innerHTML = "";
  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "debug-empty";
    empty.textContent = "No events recorded yet.";
    root.appendChild(empty);
    return;
  }
  for (const ev of events) {
    const row = document.createElement("div");
    row.className = "debug-row";
    const ts = document.createElement("span");
    ts.className = "ts";
    ts.textContent = formatTimestamp(ev.at || ev.timestamp);
    const lvl = document.createElement("span");
    lvl.className = `lvl-${(ev.level || "info").toLowerCase()}`;
    const summaryParts = [];
    if (ev.type) summaryParts.push(ev.type);
    if (ev.message) summaryParts.push(ev.message);
    if (ev.error) summaryParts.push(`error: ${ev.error}`);
    if (!summaryParts.length) summaryParts.push(JSON.stringify(ev));
    lvl.textContent = summaryParts.join(" — ");
    row.appendChild(ts);
    row.appendChild(lvl);
    root.appendChild(row);
  }
}

async function copyDebugLog() {
  const stored = await chrome.storage.local.get(["debugEvents"]);
  const events = Array.isArray(stored.debugEvents) ? stored.debugEvents : [];
  const text = events
    .map((ev) => `[${formatTimestamp(ev.at || ev.timestamp)}] ${ev.type || ""} ${ev.message || ""} ${ev.error || ""}`.trim())
    .join("\n");
  try {
    await navigator.clipboard.writeText(text || "(empty)");
    setStatus($("logStatus"), "Copied to clipboard.", "ok");
  } catch (err) {
    setStatus($("logStatus"), `Copy failed: ${err.message || err}`, "error");
  }
}

async function clearDebugLog() {
  await chrome.storage.local.set({ debugEvents: [] });
  await renderDebugLog();
  setStatus($("logStatus"), "Debug log cleared.", "ok");
}

async function init() {
  await loadSettings();
  await renderDebugLog();

  $("saveApiBase").addEventListener("click", saveApiBase);
  $("testConnection").addEventListener("click", testConnection);
  $("saveBehavior").addEventListener("click", saveBehavior);
  $("clearData").addEventListener("click", clearLocalData);
  $("refreshLog").addEventListener("click", renderDebugLog);
  $("copyLog").addEventListener("click", copyDebugLog);
  $("clearLog").addEventListener("click", clearDebugLog);

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && "debugEvents" in changes) {
      renderDebugLog();
    }
  });
}

init();
