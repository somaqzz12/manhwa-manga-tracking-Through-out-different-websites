async function sendMessage(msg) {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

async function init() {
  const apiBaseInput = document.getElementById("apiBase");
  const res = await sendMessage({ type: "GET_SETTINGS" });
  apiBaseInput.value = res?.ok ? (res.data.apiBase || "http://127.0.0.1:5000") : "http://127.0.0.1:5000";

  document.getElementById("openDashboard").addEventListener("click", () => {
    const base = (apiBaseInput.value || "http://127.0.0.1:5000").trim().replace(/\/$/, "");
    chrome.tabs.create({ url: `${base}/` });
  });
  document.getElementById("saveApiBase").addEventListener("click", async () => {
    const raw = (apiBaseInput.value || "").trim();
    const result = await sendMessage({ type: "SET_API_BASE", payload: { apiBase: raw } });
    setStatus(result?.ok
      ? `Backend URL saved: ${result.apiBase}`
      : `Failed to save backend URL: ${result?.error || "unknown error"}`);
  });
  document.getElementById("manualAdd").addEventListener("click", async () => {
    setStatus("Checking current page...");
    const result = await sendMessage({ type: "TRACK_TAB_NOW" });
    if (!result?.ok) {
      setStatus(`Manual add failed:\n${result?.error || "Unknown error"}`);
      return;
    }
    setStatus("Added successfully. Open dashboard to view.");
  });
}

init();
