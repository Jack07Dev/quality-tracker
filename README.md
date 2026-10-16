# Quality Inspection Tracker

A mobile-first web app for shop-floor supervisors at Arvind plants to log, track and resolve fabric quality defects, replacing paper registers.

**Stack:** Python (FastAPI) · SQLite · plain HTML/CSS/JavaScript (ES modules, **no build step**) · Docker optional

## Run it (under 5 minutes)

### Option A: Python 3.10+ (no Docker, no Node)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open **http://localhost:8000**. That's it: this one process serves the UI and the API. The database is created at `backend/data/tracker.db` on first start.

### Option B: Docker
```bash
docker compose up --build
```
Open http://localhost:8000. Data persists in a Docker volume.

### Run the tests
```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

### Try it on a real phone
Run `uvicorn app.main:app --host 0.0.0.0`, then open `http://<your-computer-LAN-IP>:8000` on a phone on the same Wi-Fi. The service worker (offline app shell) only registers on `https://` or `localhost`; queued offline *entries* still work over plain HTTP.

Interactive API docs: http://localhost:8000/docs
Editing the frontend? Just refresh the browser (hard refresh `Ctrl+Shift+R` if the service worker serves a cached copy).

## How to use the app
1. **Log:** pick the date, type the machine/line ID, choose defect type and severity, add optional remarks, tap *Log inspection*. Date and machine stay filled so you can log several defects on the same line quickly.
2. **Inspections:** every logged inspection. Open *Filters & sort* to filter by severity, status and date range, or change the sort order. On an Open item tap *Resolve…*, write what was done (required) and confirm.
3. **Summary:** Open/Resolved counts per severity. Tap a number to jump to that filtered list.

## Features
- All four required features: log, sortable/filterable list, resolve with mandatory note (enforced in UI *and* API), summary by severity.
- **Bonus: offline logging.** If the network is down, entries are saved in `localStorage` and synced automatically (on reconnect, on load, and every 30s). Each entry carries a client-generated ID so retries never create duplicates.
- **Bonus: mock SAP webhook** (`POST /api/sap-webhook`, below).
- **Not done:** authentication (see "What I cut").

## API

All success responses are `{"data": ...}` (lists add `"meta": {"count": n}`). All errors are `{"error": {"code", "message", "details"?}}`.

| Method & path | Purpose | Success | Errors |
|---|---|---|---|
| `POST /api/inspections` | Create | `201` (`200` if `client_id` was already used) | `422` |
| `GET /api/inspections` | List. Query: `severity`, `status`, `date_from`, `date_to`, `sort` (`inspection_date`\|`created_at`\|`severity`\|`status`\|`machine_id`), `order` (`asc`\|`desc`) | `200` | `422` |
| `GET /api/inspections/{id}` | Fetch one | `200` | `404` |
| `POST /api/inspections/{id}/resolve` | Body `{"resolution_note": "..."}` | `200` | `404`, `409` already resolved, `422` empty note |
| `GET /api/summary` | Counts by severity × status, plus totals | `200` | |
| `POST /api/sap-webhook` | Mock SAP QM notification | `201` (`200` on replay) | `401`, `422` |
| `GET /api/health` | Liveness | `200` | |

Create body:
```json
{"inspection_date": "2026-10-16", "machine_id": "LOOM-12", "defect_type": "Weave Defect",
 "severity": "Major", "remarks": "Broken pick near selvedge", "client_id": "optional-uuid"}
```

### SAP webhook payload
```json
{
  "notification_id": "QN-100234",
  "inspection_date": "2026-10-16",
  "work_center": "LOOM-07",
  "defect_code": "SHADE",
  "severity": "Critical",
  "text": "Batch 4 shade drift"
}
```
- `defect_code` maps `WEAVE`→Weave Defect, `SHADE`→Shade Variation, `HOLE`→Hole/Tear, `COUNT`→Count Deviation; anything else → Other (case-insensitive).
- `work_center` becomes the machine/line ID; `text` becomes remarks.
- Idempotent on `notification_id`: SAP re-sending the same notification returns `200` with the existing record.
- If the env var `SAP_WEBHOOK_SECRET` is set, requests must send a matching `X-SAP-Secret` header (otherwise `401`).

```bash
curl -X POST localhost:8000/api/sap-webhook -H 'Content-Type: application/json' \
  -d '{"notification_id":"QN-1","inspection_date":"2026-10-16","work_center":"LOOM-07","defect_code":"HOLE","severity":"Major"}'
```

## Project layout
```
backend/app/
  main.py       routes + central error handling + serves the frontend
  schemas.py    Pydantic request validation
  repo.py       every SQL statement
  db.py         SQLite connection + schema
backend/tests/  API tests (11)
frontend/
  index.html, style.css, sw.js
  js/
    main.js     tabs, offline banner, sync scheduling
    api.js      fetch wrapper + ApiError
    queue.js    offline queue (localStorage) + sync
    dom.js      element builder + date helpers
    state.js    shared filter state
    toast.js
    views/      log.js · list.js · summary.js  (one file per screen)
```

## Assumptions
- Single plant, single user role: any supervisor can log and resolve. No record of *who* did it.
- "Date" is the date the defect was observed (may be backdated), not necessarily today.
- Machine/line ID is free text, as specified. No master list or normalisation (`loom-12` ≠ `LOOM-12`).
- Resolution is one-way (no re-opening) and happens once.
- The SAP payload shape is invented, since no real contract was provided.
- Date-range filter is inclusive on both ends and applies to the inspection date.

## Architecture decisions
- **FastAPI + stdlib `sqlite3`, no ORM.** One table and five queries, so raw SQL in a single `repo.py` is easier to read than an ORM layer and removes dependencies and setup failures. Pydantic validates input and generates the API docs. All values are bound parameters; the only interpolated fragment (`ORDER BY`) comes from a fixed allow-list. SQLite `CHECK` constraints back up the validation.
- **Plain JavaScript ES modules, no framework or bundler.** The UI is three screens, so a framework would add a Node toolchain, install steps and a larger download for little gain. Splitting by responsibility (one module per screen, plus api/queue/dom helpers) keeps each file small. One origin served by the API means no CORS and a single process. Rendering uses text nodes only, so remarks can't inject HTML. I prototyped React-based versions too and chose this for payload size on a phone and zero-friction setup.
- **Idempotency keys instead of sync logic.** Offline entries get a client-generated ID stored in a `UNIQUE external_ref` column (the SAP webhook reuses it as `sap:<id>`), so "retry until it works" is safe without conflict resolution.
- **Consistent API contract.** One envelope for success, one for errors (including framework 404s/422s), meaningful status codes (`201`, `409`, `422`) and a dedicated `/resolve` action endpoint because resolving has business rules (note required, only once; enforced by a conditional `UPDATE`).

## What I cut / would do differently with more time
- **Authentication.** Skipped as optional. Next: login with per-supervisor accounts and `created_by` / `resolved_by` columns. Today the API is open, so deploy only on a trusted network.
- **Offline is partial.** Creating works offline; viewing, resolving and the summary need a connection. A fuller version would cache the list in IndexedDB and queue resolves with conflict handling.
- **Pagination.** The list returns everything. Fine for thousands of rows in SQLite, not for years of data; I'd add cursor pagination.
- **Machine ID master data.** A dropdown/autocomplete from plant master data (or SAP work centers) would stop typos fragmenting the data.
- **Photos** of the defect, which supervisors would likely want.
- **Migrations.** `CREATE TABLE IF NOT EXISTS` is enough for v1; I'd add numbered SQL migrations before the schema changes.
- **Frontend tests.** The backend has API tests; the UI has none automated (Playwright would be next). It is designed for 390px (single column, 48px+ tap targets, 16px inputs to avoid iOS zoom).
- **Postgres.** SQLite in WAL mode suits one container and dozens of supervisors; multiple app instances would need Postgres.
