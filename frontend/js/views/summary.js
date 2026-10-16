import { api, ApiError } from "../api.js";
import { $, h } from "../dom.js";
import { SEVERITIES } from "../state.js";

/** onPick(severity, status) is called when a count is tapped (main.js jumps to the filtered list). */
export async function loadSummary(onPick) {
  const wrap = $("#summary");
  try {
    const { data } = await api("/summary");
    const stat = (n, label, sev, status) =>
      h("button", { class: "stat", type: "button", onclick: () => onPick(sev, status) }, h("b", {}, String(n)), h("span", {}, label));

    wrap.replaceChildren(
      h("section", { class: "sum-card totals" }, h("h2", {}, "All severities"),
        h("div", { class: "stats" }, stat(data.totals.open, "Open", "", "Open"), stat(data.totals.resolved, "Resolved", "", "Resolved"))),
      ...SEVERITIES.map((s) => h("section", { class: `sum-card sev-${s.toLowerCase()}` }, h("h2", {}, s),
        h("div", { class: "stats" },
          stat(data.by_severity[s].open, "Open", s, "Open"),
          stat(data.by_severity[s].resolved, "Resolved", s, "Resolved")))),
      h("p", { class: "meta" }, "Tap a number to see those inspections."));
  } catch (e) {
    wrap.replaceChildren(h("p", { class: "empty" }, e instanceof ApiError ? e.full : "You're offline. Reconnect to view the summary."));
  }
}
