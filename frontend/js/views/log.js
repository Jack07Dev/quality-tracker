import { api, ApiError } from "../api.js";
import { $, today, uid } from "../dom.js";
import { enqueue } from "../queue.js";
import { toast } from "../toast.js";

export function initLog({ onQueued }) {
  const form = $("#log-form");
  const errorEl = $("#log-error");
  const showError = (msg) => { errorEl.textContent = msg; errorEl.hidden = !msg; };

  form.inspection_date.value = today();

  // After logging, keep date + machine (supervisors usually log several defects per line); clear the rest.
  const reset = () => {
    form.remarks.value = "";
    form.querySelectorAll("input[name=severity]").forEach((r) => (r.checked = false));
    form.defect_type.selectedIndex = 0;
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    const fd = new FormData(form);
    const payload = {
      inspection_date: fd.get("inspection_date"),
      machine_id: String(fd.get("machine_id") || "").trim(),
      defect_type: fd.get("defect_type"),
      severity: fd.get("severity"),
      remarks: String(fd.get("remarks") || "").trim() || null,
      client_id: uid(), // makes retries (including offline sync) idempotent server-side
    };
    if (!payload.machine_id) return showError("Machine / line ID is required.");

    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      await api("/inspections", { method: "POST", body: JSON.stringify(payload) });
      toast("Inspection logged");
      reset();
    } catch (err) {
      if (err instanceof ApiError) {
        showError(err.full);
      } else { // network failure -> keep it on the phone and sync later
        enqueue(payload);
        onQueued();
        toast("You're offline. Saved on this phone and will sync automatically.");
        reset();
      }
    } finally {
      btn.disabled = false;
    }
  });
}
