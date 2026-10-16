import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("SAP_WEBHOOK_SECRET", raising=False)
    from app.main import app
    with TestClient(app) as c:  # context manager runs lifespan -> creates schema
        yield c


def make(client, **over):
    body = {"inspection_date": "2026-10-10", "machine_id": "Loom-12", "defect_type": "Weave Defect",
            "severity": "Major", **over}
    return client.post("/api/inspections", json=body)


def test_create_and_get(client):
    r = make(client, remarks="  slub  ")
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["status"] == "Open" and data["remarks"] == "slub"
    assert client.get(f"/api/inspections/{data['id']}").json()["data"]["machine_id"] == "Loom-12"


@pytest.mark.parametrize("override", [
    {"machine_id": "   "}, {"severity": "Huge"}, {"defect_type": "Stain"}, {"inspection_date": "yesterday"},
])
def test_create_validation(client, override):
    r = make(client, **override)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_client_id_is_idempotent(client):
    first = make(client, client_id="abcdef123456")
    second = make(client, client_id="abcdef123456")
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert client.get("/api/inspections").json()["meta"]["count"] == 1


def test_resolve_requires_note_and_only_once(client):
    iid = make(client).json()["data"]["id"]
    assert client.post(f"/api/inspections/{iid}/resolve", json={"resolution_note": "  "}).status_code == 422
    assert client.post(f"/api/inspections/{iid}/resolve", json={}).status_code == 422
    ok = client.post(f"/api/inspections/{iid}/resolve", json={"resolution_note": "Re-threaded warp"})
    assert ok.status_code == 200 and ok.json()["data"]["status"] == "Resolved"
    assert ok.json()["data"]["resolved_at"]
    again = client.post(f"/api/inspections/{iid}/resolve", json={"resolution_note": "x"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_resolved"
    assert client.post("/api/inspections/999/resolve", json={"resolution_note": "x"}).status_code == 404


def test_filters_and_sorting(client):
    make(client, severity="Critical", inspection_date="2026-10-01", machine_id="A")
    make(client, severity="Minor", inspection_date="2026-10-05", machine_id="B")
    done = make(client, severity="Major", inspection_date="2026-10-09", machine_id="C").json()["data"]["id"]
    client.post(f"/api/inspections/{done}/resolve", json={"resolution_note": "fixed"})

    ids = lambda q: [r["machine_id"] for r in client.get(f"/api/inspections{q}").json()["data"]]
    assert ids("") == ["C", "B", "A"]  # newest first by default
    assert ids("?status=Open") == ["B", "A"]
    assert ids("?severity=Critical") == ["A"]
    assert ids("?date_from=2026-10-02&date_to=2026-10-08") == ["B"]
    assert ids("?sort=severity&order=asc") == ["A", "C", "B"]
    assert client.get("/api/inspections?date_from=2026-11-01&date_to=2026-10-01").status_code == 422
    assert client.get("/api/inspections?sort=password").status_code == 422


def test_summary(client):
    make(client, severity="Critical")
    make(client, severity="Critical")
    done = make(client, severity="Minor").json()["data"]["id"]
    client.post(f"/api/inspections/{done}/resolve", json={"resolution_note": "ok"})
    s = client.get("/api/summary").json()["data"]
    assert s["by_severity"]["Critical"] == {"open": 2, "resolved": 0}
    assert s["by_severity"]["Minor"] == {"open": 0, "resolved": 1}
    assert s["by_severity"]["Major"] == {"open": 0, "resolved": 0}
    assert s["totals"] == {"open": 2, "resolved": 1}


def test_sap_webhook(client, monkeypatch):
    payload = {"notification_id": "QN-1001", "inspection_date": "2026-10-12", "work_center": "LOOM-07",
               "defect_code": "shade", "severity": "Critical", "text": "Batch 4 shade drift"}
    r = client.post("/api/sap-webhook", json=payload)
    assert r.status_code == 201 and r.json()["data"]["defect_type"] == "Shade Variation"
    assert client.post("/api/sap-webhook", json=payload).status_code == 200  # replay
    other = client.post("/api/sap-webhook", json={**payload, "notification_id": "QN-2", "defect_code": "ZZZ"})
    assert other.json()["data"]["defect_type"] == "Other"

    monkeypatch.setenv("SAP_WEBHOOK_SECRET", "s3cret")
    assert client.post("/api/sap-webhook", json={**payload, "notification_id": "QN-3"}).status_code == 401
    ok = client.post("/api/sap-webhook", json={**payload, "notification_id": "QN-3"},
                     headers={"X-SAP-Secret": "s3cret"})
    assert ok.status_code == 201


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
