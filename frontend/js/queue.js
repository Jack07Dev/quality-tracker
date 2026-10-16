// Offline queue: inspections logged without connectivity wait in localStorage and are
// replayed later. Each carries a client_id, so the server de-duplicates retries.
import { api, ApiError } from "./api.js";
import { toast } from "./toast.js";

const KEY = "qt.pending";
let syncing = false;

const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; } };
const save = (q) => localStorage.setItem(KEY, JSON.stringify(q));

export const pendingCount = () => load().length;
export const enqueue = (payload) => save([...load(), payload]);

/** Sends queued entries in order. Returns how many were synced. */
export async function syncPending() {
  if (syncing || !navigator.onLine) return 0;
  syncing = true;
  let sent = 0;
  try {
    for (let q = load(); q.length; q = load()) {
      try {
        await api("/inspections", { method: "POST", body: JSON.stringify(q[0]) });
        sent++;
      } catch (e) {
        // Network error or 5xx: stop and retry later. A 4xx can never succeed, so drop it
        // rather than block every entry behind it.
        if (!(e instanceof ApiError) || e.status >= 500) break;
        toast(`Dropped an invalid queued entry: ${e.message}`);
      }
      save(q.slice(1));
    }
  } finally {
    syncing = false;
  }
  return sent;
}
