async function sendMessage(msg) {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

function renderDebug(events) {
  const debugOutput = document.getElementById("debugOutput");
  if (!events?.length) {
    debugOutput.textContent = "No debug events yet.";
    return;
  }
  const lines = events
    .slice(-8)
    .reverse()
    .map((e) => `${e.at || "unknown-time"} | ${e.event || "event"}\n${JSON.stringify(e.details || e, null, 2)}`);
  debugOutput.textContent = lines.join("\n\n");
}

async function init() {
  const box = document.getElementById("autoprompt");
  const debugBox = document.getElementById("debugMode");
  const res = await sendMessage({ type: "GET_SETTINGS" });
  box.checked = res?.ok ? !!res.data.autoprompt : true;
  debugBox.checked = res?.ok ? !!res.data.debugMode : false;

  box.addEventListener("change", async () => {
    await sendMessage({ type: "SET_AUTOPROMPT", payload: { autoprompt: box.checked } });
  });
  debugBox.addEventListener("change", async () => {
    await sendMessage({ type: "SET_DEBUG_MODE", payload: { debugMode: debugBox.checked } });
  });

  document.getElementById("openDashboard").addEventListener("click", () => {
    chrome.tabs.create({ url: "http://127.0.0.1:5000/" });
  });
  document.getElementById("mergeDuplicates").addEventListener("click", async () => {
    const result = await sendMessage({ type: "MERGE_DUPLICATES" });
    const message = result?.ok
      ? `Merged ${result.data?.merged_groups || 0} groups, deleted ${result.data?.deleted_bookmarks || 0} duplicate rows.`
      : `Merge failed: ${result?.error || "unknown error"}`;
    document.getElementById("debugOutput").textContent = message;
  });
  document.getElementById("refreshDebug").addEventListener("click", async () => {
    const debugRes = await sendMessage({ type: "GET_DEBUG_EVENTS" });
    renderDebug(debugRes?.ok ? debugRes.data : []);
  });

  const debugRes = await sendMessage({ type: "GET_DEBUG_EVENTS" });
  renderDebug(debugRes?.ok ? debugRes.data : []);
}

init();
