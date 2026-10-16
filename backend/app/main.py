"""Quality Inspection Tracker API + static frontend."""
import hmac
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db, repo
from .schemas import InspectionCreate, ResolveRequest, SapPayload, Severity, Status

FRONTEND_DIR = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend"))

SAP_DEFECT_CODES = {
    "WEAVE": "Weave Defect",
    "SHADE": "Shade Variation",
    "HOLE": "Hole/Tear",
    "COUNT": "Count Deviation",
}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code, self.code, self.message, self.details = status_code, code, message, details


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Quality Inspection Tracker", version="1.0.0", lifespan=lifespan)


# ---- Errors: every error is {"error": {"code", "message", "details"?}} ----
def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return _error(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return _error(422, "validation_error", "Invalid request", details)


@app.exception_handler(StarletteHTTPException)
async def http_handler(_: Request, exc: StarletteHTTPException):
    codes = {404: "not_found", 405: "method_not_allowed"}
    return _error(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))


def get_db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


# ---- Routes ----
@app.get("/api/health")
def health():
    return {"data": {"status": "ok"}}


@app.post("/api/inspections", status_code=201)
def create_inspection(body: InspectionCreate, response: Response, conn=Depends(get_db)):
    data = body.model_dump(exclude={"client_id"})
    ref = f"client:{body.client_id}" if body.client_id else None
    row, created = repo.create(conn, data, ref)
    if not created:
        response.status_code = 200  # idempotent replay of an offline-queued entry
    return {"data": row}


@app.get("/api/inspections")
def list_inspections(
    severity: Optional[Severity] = None,
    status: Optional[Status] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort: Literal["inspection_date", "created_at", "severity", "status", "machine_id"] = "inspection_date",
    order: Literal["asc", "desc"] = "desc",
    conn=Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise ApiError(422, "validation_error", "date_from must be on or before date_to")
    rows = repo.list_all(conn, severity=severity, status=status, date_from=date_from,
                         date_to=date_to, sort=sort, order=order)
    return {"data": rows, "meta": {"count": len(rows)}}


@app.get("/api/inspections/{inspection_id}")
def get_inspection(inspection_id: int, conn=Depends(get_db)):
    row = repo.get(conn, inspection_id)
    if row is None:
        raise ApiError(404, "not_found", f"Inspection {inspection_id} not found")
    return {"data": row}


@app.post("/api/inspections/{inspection_id}/resolve")
def resolve_inspection(inspection_id: int, body: ResolveRequest, conn=Depends(get_db)):
    try:
        row = repo.resolve(conn, inspection_id, body.resolution_note)
    except repo.AlreadyResolved:
        raise ApiError(409, "already_resolved", "This inspection is already resolved")
    if row is None:
        raise ApiError(404, "not_found", f"Inspection {inspection_id} not found")
    return {"data": row}


@app.get("/api/summary")
def get_summary(conn=Depends(get_db)):
    return {"data": repo.summary(conn)}


@app.post("/api/sap-webhook", status_code=201)
def sap_webhook(body: SapPayload, response: Response, conn=Depends(get_db),
                x_sap_secret: Optional[str] = Header(default=None)):
    """Mock SAP QM integration. Idempotent on notification_id."""
    secret = os.getenv("SAP_WEBHOOK_SECRET")
    if secret and not hmac.compare_digest((x_sap_secret or "").encode(), secret.encode()):
        raise ApiError(401, "unauthorized", "Invalid or missing X-SAP-Secret header")
    data = {
        "inspection_date": body.inspection_date,
        "machine_id": body.work_center,
        "defect_type": SAP_DEFECT_CODES.get(body.defect_code.upper(), "Other"),
        "severity": body.severity,
        "remarks": body.text,
    }
    row, created = repo.create(conn, data, f"sap:{body.notification_id}")
    if not created:
        response.status_code = 200
    return {"data": row}


# Static frontend (plain HTML/CSS/JS, no build step) mounted last so /api/* routes win.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
