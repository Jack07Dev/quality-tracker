// Entry point: tab navigation, offline banner and sync scheduling. Feature code lives in views/.
import { $ } from "./dom.js";
import { pendingCount, syncPending } from "./queue.js";
import { resetFilters } from "./state.js";
import { toast } from "./toast.js";
import { initList, loadList } from "./views/list.js";
import { initLog } from "./views/log.js";
import { loadSummary } from "./views/summary.js";

const TABS = ["log", "list", "summary"];
let current = "log";

function setTab(name) {
  current = name;
  for (const t of TABS) $(`#view-${t}`).hidden = t !== name;
  document.querySelectorAll(".tabs button").forEach((b) => {
    if (b.dataset.tab === name) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  refresh();
  window.scrollTo(0, 0);
}

function refresh() {
  if (current === "list") loadList();
  if (current === "summary") loadSummary(showFiltered);
}

function showFiltered(severity, status) {
  resetFilters({ severity, status });
  setTab("list");
}

function updateNetbar() {
  const parts = [];
  if (!navigator.onLine) parts.push("Offline");
  if (pendingCount()) parts.push(`${pendingCount()} waiting to sync`);
  const bar = $("#netbar");
  bar.hidden = parts.length === 0;
  bar.textContent = parts.join(" · ");
}

async function sync() {
  const sent = await syncPending();
  updateNetbar();
  if (sent) {
    toast(`Synced ${sent} offline ${sent === 1 ? "entry" : "entries"}`);
    refresh();
  }
}

document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
initLog({ onQueued: updateNetbar });
initList();
window.addEventListener("online", () => { updateNetbar(); sync(); });
window.addEventListener("offline", updateNetbar);
setInterval(sync, 30000);
updateNetbar();
sync();

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
