"""Quick smoke-test script for manual demo verification.

Sends a small end-to-end request sequence to a running local backend.
"""

from __future__ import annotations

import json

import httpx

BASE_URL = "http://127.0.0.1:8000"


def _auth_headers(role: str, doctor_id: str | None = None) -> dict[str, str]:
    token = f"role:{role}|email:{role}@example.com|user_id:{role}-smoke"
    headers = {"Authorization": f"Bearer {token}"}
    if doctor_id:
        headers["X-Doctor-Id"] = doctor_id
    return headers


def _post(path: str, payload: dict, role: str, doctor_id: str | None = None) -> dict:
    headers = _auth_headers(role, doctor_id=doctor_id)
    response = httpx.post(f"{BASE_URL}{path}", json=payload, headers=headers, timeout=20)
    print(path, response.status_code)
    return response.json()


def _get(path: str, role: str) -> dict:
    response = httpx.get(f"{BASE_URL}{path}", headers=_auth_headers(role), timeout=20)
    print(path, response.status_code)
    return response.json()


def main() -> None:
    intake = _post(
        "/ai/process_intake",
        {
            "visit_id": "demo-visit-001",
            "age_years": 5,
            "weight_kg": 18,
            "symptoms_text": "fever, cough, fast breathing since yesterday",
            "duration_days": 1,
            "vitals": {"rr": 40, "temp_c": 39.2},
        },
        role="nurse",
    )
    dose = _post(
        "/ai/dose-check",
        {
            "visit_id": "demo-visit-001",
            "drug": "amoxicillin",
            "age_years": 5,
            "weight_kg": 18,
            "frequency_per_day": 2,
            "chosen_dose_mg_per_day": 1600,
        },
        role="doctor",
    )
    override = _post(
        "/med-orders/demo-med-001/override",
        {"reason": "Specialist instruction based on prior response"},
        role="doctor",
        doctor_id="doc-demo-1",
    )
    metrics = _get("/admin/metrics", role="admin")

    print("\n=== Smoke Summary ===")
    print(json.dumps({"intake": intake, "dose": dose, "override": override, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
