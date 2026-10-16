import { api, ApiError } from "../api.js";
import { $, fmtDate, fmtDateTime, h } from "../dom.js";
import { filters, resetFilters } from "../state.js";
import { toast } from "../toast.js";

const FILTER_INPUTS = { "#f-severity": "severity", "#f-status": "status", "#f-from": "date_from", "#f-to": "date_to", "#f-sort": "sort" };

export function initList() {
  for (const [sel, key] of Object.entries(FILTER_INPUTS)) {
    $(sel).addEventListener("change", (e) => { filters[key] = e.target.value; loadList(); });
  }
  $("#f-clear").addEventListener("click", () => { resetFilters(); loadList(); });
}

function syncFilterInputs() {
  for (const [sel, key] of Object.entries(FILTER_INPUTS)) $(sel).value = filters[key];
  const active = ["severity", "status", "date_from", "date_to"].filter((k) => filters[k]).length;
  const pill = $("#filter-count");
  pill.hidden = !active;
  pill.textContent = `${active} active`;
}

let requestId = 0; // ignore stale responses if filters change quickly

export async function loadList() {
  syncFilterInputs();
  const params = new URLSearchParams();
  for (const k of ["severity", "status", "date_from", "date_to"]) if (filters[k]) params.set(k, filters[k]);
  const [sort, order] = filters.sort.split(":");
  params.set("sort", sort);
  params.set("order", order);

  const mine = ++requestId;
  const list = $("#list");
  try {
    const { data, meta } = await api("/inspections?" + params);
    if (mine !== requestId) return;
    $("#list-meta").textContent = `${meta.count} ${meta.count === 1 ? "inspection" : "inspections"}`;
    list.replaceChildren(...(data.length ? data.map(card) : [h("p", { class: "empty" }, "No inspections match these filters.")]));
  } catch (e) {
    if (mine !== requestId) return;
    $("#list-meta").textContent = "";
    list.replaceChildren(h("p", { class: "empty" },
      e instanceof ApiError ? e.full : "You're offline. Reconnect to view inspections."));
  }
}

function card(i) {
  const resolved = i.status === "Resolved";
  const note = h("textarea", { rows: 3, maxlength: 1000, placeholder: "What was done to resolve this? (required)", "aria-label": "Resolution note" });
  const err = h("p", { class: "error", hidden: true });
  const showErr = (msg) => { err.textContent = msg; err.hidden = false; };

  const confirm = h("button", { class: "primary", type: "button", onclick: async () => {
    if (!note.value.trim()) { showErr("A resolution note is required."); note.focus(); return; }
    confirm.disabled = true;
    try {
      await api(`/inspections/${i.id}/resolve`, { method: "POST", body: JSON.stringify({ resolution_note: note.value }) });
      toast("Marked as resolved");
      loadList();
    } catch (e) {
      showErr(e instanceof ApiError ? e.full : "You're offline. Try again when connected.");
      confirm.disabled = false;
    }
  } }, "Confirm resolved");
  const cancel = h("button", { class: "secondary", type: "button", onclick: () => (box.hidden = true) }, "Cancel");
  const box = h("div", { class: "resolve-box", hidden: true }, note, err, h("div", { class: "btns" }, confirm, cancel));

  return h("article", { class: `card sev-${i.severity.toLowerCase()}` },
    h("div", { class: "row" },
      h("span", { class: "machine" }, i.machine_id),
      h("span", { class: `badge ${i.status.toLowerCase()}` }, i.status)),
    h("div", { class: "sub" }, `${i.severity} · ${i.defect_type} · ${fmtDate(i.inspection_date)}`),
    i.remarks && h("p", { class: "text" }, i.remarks),
    resolved && h("div", { class: "resolution" },
      h("b", {}, "Resolution: "), i.resolution_note, " ",
      h("span", { class: "sub" }, `(${fmtDateTime(i.resolved_at)})`)),
    !resolved && h("div", { class: "actions" },
      h("button", { class: "secondary", type: "button", onclick: () => { box.hidden = !box.hidden; if (!box.hidden) note.focus(); } }, "Resolve…")),
    box);
}
