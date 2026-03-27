"""API contract tests.

These tests verify that key endpoints exist and return expected response shapes.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path) -> TestClient:
    os.environ["CLINIQ_DB_PATH"] = str(tmp_path / "test_cliniq.db")
    os.environ["CLINIQ_AUTH_MODE"] = "stub"
    from backend.main import app

    return TestClient(app)


def _auth_headers(role: str, doctor_id: str | None = None) -> dict[str, str]:
    token = f"role:{role}|email:{role}@example.com|user_id:{role}-1"
    headers = {"Authorization": f"Bearer {token}"}
    if doctor_id:
        headers["X-Doctor-Id"] = doctor_id
    return headers


def test_health_and_root(tmp_path: Path) -> None:
    client = _client(tmp_path)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    root = client.get("/")
    assert root.status_code == 200
    assert "docs" in root.json()


def test_process_intake_contract_shape(tmp_path: Path) -> None:
    client = _client(tmp_path)
    payload = {
        "visit_id": "visit-001",
        "age_years": 5,
        "weight_kg": 18,
        "symptoms_text": "my name is John Doe, fever and fast breathing since yesterday",
        "duration_days": 1,
        "vitals": {"rr": 40, "temp_c": 39.2},
    }
    response = client.post("/ai/process_intake", json=payload, headers=_auth_headers("nurse"))
    assert response.status_code == 200
    body = response.json()
    assert set(["visit_id", "triage", "summary", "audit_event_id"]).issubset(body.keys())
    assert "urgency_level" in body["triage"]


def test_dose_check_unsafe_and_safe(tmp_path: Path) -> None:
    client = _client(tmp_path)
    common = {
        "visit_id": "visit-dose",
        "drug": "amoxicillin",
        "age_years": 5,
        "weight_kg": 18,
        "frequency_per_day": 2,
    }
    unsafe = client.post(
        "/ai/dose-check",
        json={**common, "chosen_dose_mg_per_day": 2000},
        headers=_auth_headers("doctor"),
    )
    assert unsafe.status_code == 200
    assert unsafe.json()["safe"] is False
    assert unsafe.json()["allow_override"] is True

    safe = client.post(
        "/ai/dose-check",
        json={**common, "chosen_dose_mg_per_day": 500},
        headers=_auth_headers("doctor"),
    )
    assert safe.status_code == 200
    assert safe.json()["safe"] is True


def test_override_and_metrics(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post(
        "/ai/process_intake",
        json={
            "visit_id": "visit-metrics",
            "age_years": 4,
            "weight_kg": 16,
            "symptoms_text": "convulsion and fever",
            "duration_days": 1,
            "vitals": {"rr": 38},
        },
        headers=_auth_headers("nurse"),
    )
    client.post(
        "/ai/dose-check",
        json={
            "visit_id": "visit-metrics",
            "drug": "amoxicillin",
            "age_years": 4,
            "weight_kg": 16,
            "frequency_per_day": 2,
            "chosen_dose_mg_per_day": 9999,
        },
        headers=_auth_headers("doctor"),
    )
    override = client.post(
        "/med-orders/m1/override",
        json={"reason": "Clinically justified by prior specialist recommendation"},
        headers=_auth_headers("doctor", doctor_id="doc-123"),
    )
    assert override.status_code == 200
    assert override.json()["override_logged"] is True

    metrics = client.get("/admin/metrics", headers=_auth_headers("admin"))
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["total_intakes"] >= 1
    assert body["unsafe_dose_warnings"] >= 1
    assert body["overrides"] >= 1


def test_error_shape_for_validation_and_forbidden(tmp_path: Path) -> None:
    client = _client(tmp_path)
    forbidden = client.get("/admin/metrics", headers=_auth_headers("nurse"))
    assert forbidden.status_code == 403
    assert "error" in forbidden.json()

    invalid = client.post("/ai/process_intake", json={"visit_id": "x"}, headers=_auth_headers("nurse"))
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_sync_scaffold_endpoints(tmp_path: Path) -> None:
    client = _client(tmp_path)
    status = client.get("/admin/sync/status", headers=_auth_headers("admin"))
    assert status.status_code == 200
    body = status.json()
    assert "configured" in body
    assert "pending" in body

    run = client.post("/admin/sync/run", headers=_auth_headers("admin"))
    assert run.status_code == 200
    assert "ok" in run.json()


def test_full_demo_endpoints_flow(tmp_path: Path) -> None:
    client = _client(tmp_path)

    ro_patient = client.post(
        "/record-officer/patients",
        json={"full_name": "RO Child", "date_of_birth": "2021-06-01", "gender": "female"},
        headers=_auth_headers("record_officer"),
    )
    assert ro_patient.status_code == 200
    ro_patient_id = ro_patient.json()["id"]

    ro_visit = client.post(
        "/record-officer/visits",
        json={"patient_id": ro_patient_id, "visit_status": "open"},
        headers=_auth_headers("record_officer"),
    )
    assert ro_visit.status_code == 200
    ro_visit_id = ro_visit.json().get("visit_id") or ro_visit.json().get("id")

    nurse_intake = client.post(
        "/nurse/process-intake",
        json={
            "visit_id": ro_visit_id,
            "age_years": 5,
            "weight_kg": 18,
            "symptoms_text": "fever and cough for one day",
            "duration_days": 1,
            "vitals": {"rr": 34},
        },
        headers=_auth_headers("nurse"),
    )
    assert nurse_intake.status_code == 200

    nurse_summary = client.post(
        "/nurse/summary",
        json={"visit_id": ro_visit_id, "transcript": "fever and cough", "patient_age": "5 years"},
        headers=_auth_headers("nurse"),
    )
    assert nurse_summary.status_code == 200

    nurse_latest = client.get(f"/nurse/visits/{ro_visit_id}/latest-intake", headers=_auth_headers("nurse"))
    assert nurse_latest.status_code == 200

    patient = client.post(
        "/patients",
        json={"full_name": "Test Child", "date_of_birth": "2021-06-01", "gender": "female", "phone": "08030000000"},
        headers=_auth_headers("record_officer"),
    )
    assert patient.status_code == 200
    patient_id = patient.json()["id"]

    visit = client.post(
        "/visits",
        json={"patient_id": patient_id, "visit_status": "open"},
        headers=_auth_headers("record_officer"),
    )
    assert visit.status_code == 200
    visit_id = visit.json()["id"]

    summary = client.post(
        "/ai/summary",
        json={"visit_id": visit_id, "transcript": "child has fever and cough for two days", "patient_age": "5 years"},
        headers=_auth_headers("nurse"),
    )
    assert summary.status_code == 200
    assert "summary" in summary.json()

    intake = client.post(
        "/ai/process_intake",
        json={
            "visit_id": visit_id,
            "age_years": 5,
            "weight_kg": 18,
            "symptoms_text": "fever and fast breathing since yesterday",
            "duration_days": 1,
            "vitals": {"rr": 40, "temp_c": 39.2},
        },
        headers=_auth_headers("nurse"),
    )
    assert intake.status_code == 200

    latest_intake = client.get(f"/visits/{visit_id}/latest-intake", headers=_auth_headers("doctor"))
    assert latest_intake.status_code == 200

    asr = client.post(
        "/asr/transcribe",
        json={"transcript_hint": "patient had fever and cough, no seizure"},
        headers=_auth_headers("doctor"),
    )
    assert asr.status_code == 200
    transcript = asr.json()["transcript"]

    convo = client.post(
        f"/visits/{visit_id}/doctor-conversation",
        json={"transcript": transcript, "patient_age": "5 years"},
        headers=_auth_headers("doctor", doctor_id="doc-1"),
    )
    assert convo.status_code == 200
    assert "soap_note" in convo.json()

    med_order = client.post(
        "/med-orders",
        json={
            "visit_id": visit_id,
            "drug_name": "amoxicillin",
            "dose_mg_per_day": 600,
            "frequency_per_day": 2,
            "is_safe": True,
            "dose_check_result": {"safe": True},
        },
        headers=_auth_headers("doctor"),
    )
    assert med_order.status_code == 200
    med_order_id = med_order.json()["id"]

    override = client.post(
        f"/med-orders/{med_order_id}/override",
        json={"reason": "Clinical judgment with close monitoring"},
        headers=_auth_headers("doctor", doctor_id="doc-1"),
    )
    assert override.status_code == 200

    logs = client.get("/admin/logs", headers=_auth_headers("admin"))
    assert logs.status_code == 200
    assert isinstance(logs.json().get("items"), list)
