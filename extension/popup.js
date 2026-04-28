async function sendMessage(msg) {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

let toastTimer = null;
function showToast(text, kind = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = text;
  toast.className = `toast ${kind}`;
  requestAnimationFrame(() => toast.classList.add("show"));
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, 2200);
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
    const text = result?.ok
      ? `Backend URL saved`
      : `Failed to save backend URL`;
    setStatus(result?.ok
      ? `Backend URL saved: ${result.apiBase}`
      : `Failed to save backend URL: ${result?.error || "unknown error"}`);
    showToast(text, result?.ok ? "success" : "error");
    document.body.classList.add("pulse");
    setTimeout(() => document.body.classList.remove("pulse"), 520);
  });
  document.getElementById("manualAdd").addEventListener("click", async () => {
    setStatus("Checking current page...");
    const result = await sendMessage({ type: "TRACK_TAB_NOW" });
    if (!result?.ok) {
      setStatus(`Manual add failed:\n${result?.error || "Unknown error"}`);
      showToast("Could not add this page", "error");
      return;
    }
    setStatus("Added successfully. Open dashboard to view.");
    showToast("Added to registry", "success");
  });
}

init();
