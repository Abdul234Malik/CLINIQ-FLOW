"""Record-officer-specific endpoints. Uses Supabase for all data."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database.supabase import supabase
from app.schemas.patient import CreatePatient, BioData, ContactInfo, StatutoryInfo, NextOfKin
from app.services import patient_service
from app.services import visit_service
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload

router = APIRouter(prefix="/record-officer", tags=["Record Officer"])

# Separate router for /patients/register - must be included BEFORE router to avoid
# /patients/{patient_id} matching "register" as patient_id (causes 405 on POST)
register_router = APIRouter(prefix="/record-officer", tags=["Record Officer"])


class PatientCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=2)
    date_of_birth: str | None = None
    gender: str | None = None
    phone: str | None = None


class VisitCreateRequest(BaseModel):
    patient_id: str = Field(...)
    reason_for_visit: str | None = None
    department: str | None = None


class FullRegistrationRequest(BaseModel):
    """Flattened registration form to map to CreatePatient."""
    pid: str | None = None  # User-entered Patient ID (e.g. PID-1234)
    firstName: str = Field(..., min_length=1)
    lastName: str = Field(..., min_length=1)
    otherNames: str | None = None
    dob: str = Field(...)
    gender: str = Field(...)
    civilStatus: str | None = None
    religion: str | None = None
    tribe: str | None = None
    nationality: str | None = None
    phone: str = Field(..., min_length=7)
    altPhone: str | None = None
    email: str | None = None
    address: str = Field(..., min_length=1)
    state: str | None = None
    lga: str | None = None
    nin: str | None = None
    nhisNumber: str | None = None
    militaryNumber: str | None = None
    education: str | None = None
    nokName: str = Field(..., min_length=1)
    nokRelationship: str = Field(...)
    nokPhone: str = Field(..., min_length=7)
    nokAddress: str | None = None
    doctorInCharge: str | None = None


# --- Full patient registration (from 4-step form) ---
# Path /register-patient avoids conflict with /patients/{patient_id} matching "register"
@register_router.post("/register-patient")
async def full_register_patient_route(
    payload: FullRegistrationRequest,
    auth: AuthContext = Depends(require_role("record_officer", "admin")),
):
    """Full 4-step registration. Saves to Supabase via patient_service."""
    try:
        dob = date.fromisoformat(payload.dob)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date_of_birth format (use YYYY-MM-DD)")
    create_payload = CreatePatient(
        primary_bio=BioData(
            first_name=payload.firstName,
            last_name=payload.lastName,
            other_name=payload.otherNames,
            date_of_birth=dob,
            gender=payload.gender,
            civil_status=payload.civilStatus,
            religion=payload.religion,
            tribe=payload.tribe,
        ),
        contact_info=ContactInfo(
            phone_number=payload.phone,
            alternative_phone=payload.altPhone,
            email=payload.email or None,
            address=payload.address,
            nationality=payload.nationality or None,
            state_of_origin=payload.state,
            lga=payload.lga,
        ),
        statutory_info=StatutoryInfo(
            nin=payload.nin,
            nhis_number=payload.nhisNumber,
            military_service_number=payload.militaryNumber,
            education=payload.education,
        ) if (payload.nin or payload.nhisNumber or payload.militaryNumber or payload.education) else None,
        next_of_kin=NextOfKin(
            full_name=payload.nokName,
            relationship=payload.nokRelationship,
            phone_number=payload.nokPhone,
            address=payload.nokAddress,
        ),
    )
    current_user = {"id": auth.user_id, "user_id": auth.user_id}
    try:
        patient = await patient_service.create_patient(create_payload, current_user, pid=payload.pid)
        return patient
    except Exception as e:
        import traceback
        err_detail = str(e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", err_detail, None),
        )


# --- Patient create (minimal - for quick registration) ---
@router.post("/patients")
def create_patient_route(
    payload: PatientCreateRequest,
    auth: AuthContext = Depends(require_role("record_officer", "admin")),
):
    """Minimal patient creation. For full registration use /api/patients."""
    parts = payload.full_name.strip().split(maxsplit=1)
    first_name = parts[0] if parts else payload.full_name
    last_name = parts[1] if len(parts) > 1 else ""
    patient_id = str(uuid.uuid4())
    data = {
        "id": patient_id,
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": payload.date_of_birth,
        "gender": payload.gender,
        "phone_number": payload.phone or "",
        "address": "",
        "next_of_kin_name": "",
        "next_of_kin_relationship": "",
        "next_of_kin_phone": "",
    }
    try:
        supabase.table("patients").insert(data).execute()
        return {**data, "created_at": ""}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", "Failed to create patient", str(e)),
        )


# --- List all patients (for Patient Records tab) ---
@router.get("/patients")
async def list_patients_route(
    search: str | None = Query(default=None, description="Optional search filter"),
    auth: AuthContext = Depends(require_role("record_officer", "admin", "nurse", "doctor")),
):
    """List all patients, optionally filtered by search. Used by Patient Records."""
    _ = auth
    patients = await patient_service.get_patients(search=search or "", search_by=None)
    if not patients:
        return []
    patient_ids = [p.get("id", "") for p in patients if p.get("id")]
    stats_map = patient_service.get_visit_stats_bulk(patient_ids)
    out = []
    for p in patients:
        pid = p.get("id", "")
        first = p.get("first_name") or ""
        last = p.get("last_name") or ""
        name = f"{first} {last}".strip() or "Unknown"
        stats = stats_map.get(pid, {"previous_visits": 0, "last_visit": "—"})
        out.append({
            "id": pid,
            "pid": p.get("pid") or pid,  # User-facing PID; fallback to id for legacy rows
            "name": name,
            "age": p.get("age"),
            "sex": p.get("gender"),
            "phone": p.get("phone_number") or p.get("alternative_phone"),
            "dob": (p.get("date_of_birth") or "")[:10],
            "address": p.get("address"),
            "previousVisits": stats["previous_visits"],
            "lastVisit": stats["last_visit"],
        })
    return out


# --- Patient search (must be before /patients/{patient_id}) ---
@router.get("/patients/search")
async def search_patients_route(
    q: str = Query(..., min_length=1),
    search_by: str = Query(default="name", description="id | pid | phone | nameDob"),
    auth: AuthContext = Depends(require_role("record_officer", "admin")),
):
    """Search patients by ID, phone, or name+dob. Returns list with previousVisits, lastVisit."""
    _ = auth
    try:
        patients = await patient_service.get_patients(search=q, search_by=search_by)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", str(e), None),
        ) from e
    if not patients:
        return []
    out = []
    for p in patients:
        pid_val = p.get("id", "")
        stats = patient_service.get_patient_visit_stats(pid_val)
        first = p.get("first_name") or ""
        last = p.get("last_name") or ""
        name = f"{first} {last}".strip() or "Unknown"
        out.append({
            "id": pid_val,
            "pid": p.get("pid") or pid_val,
            "name": name,
            "age": p.get("age"),
            "sex": p.get("gender"),
            "phone": p.get("phone_number") or p.get("alternative_phone"),
            "dob": p.get("date_of_birth", "")[:10] if p.get("date_of_birth") else "",
            "previousVisits": stats["previous_visits"],
            "lastVisit": stats["last_visit"],
        })
    return out


@router.get("/patients/{patient_id}")
async def get_patient_route(
    patient_id: str,
    auth: AuthContext = Depends(require_role("record_officer", "admin", "nurse", "doctor")),
):
    _ = auth
    try:
        patient = await patient_service.get_patient_by_id(patient_id)
        stats = patient_service.get_patient_visit_stats(patient_id)
        first = patient.get("first_name") or ""
        last = patient.get("last_name") or ""
        name = f"{first} {last}".strip() or "Unknown"
        return {
            **patient,
            "name": name,
            "sex": patient.get("gender"),
            "phone": patient.get("phone_number"),
            "previousVisits": stats["previous_visits"],
            "lastVisit": stats["last_visit"],
        }
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=error_payload("NOT_FOUND", "Patient not found", {"patient_id": patient_id}),
        )


# --- Visits ---
@router.post("/visits")
async def create_visit_route(
    payload: VisitCreateRequest,
    auth: AuthContext = Depends(require_role("record_officer", "admin")),
):
    """Create a new visit. Status: WAITING_FOR_TRIAGE, triage_status: PENDING."""
    try:
        patient = await patient_service.get_patient_by_id(payload.patient_id)
    except Exception:
        patient = None
    if not patient:
        raise HTTPException(
            status_code=404,
            detail=error_payload("NOT_FOUND", "Patient not found", {"patient_id": payload.patient_id}),
        )
    try:
        visit = visit_service.create_visit(
            patient_id=payload.patient_id,
            created_by=auth.user_id,
            reason_for_visit=payload.reason_for_visit,
            department=payload.department,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        err_msg = str(e)
        if hasattr(e, "args") and e.args:
            err_msg = str(e.args[0]) if isinstance(e.args[0], str) else err_msg
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", err_msg, None),
        ) from e
    first = patient.get("first_name") or ""
    last = patient.get("last_name") or ""
    patient_name = f"{first} {last}".strip() or "Unknown"
    created_raw = visit.get("created_at")
    # Supabase may return datetime object; normalize to string
    if hasattr(created_raw, "isoformat"):
        created = created_raw.isoformat()
    else:
        created = str(created_raw) if created_raw else ""
    time_str = created[11:16] if len(created) >= 16 else created
    return {
        "visit_id": visit.get("id"),
        "patient_id": payload.patient_id,
        "patient_name": patient_name,
        "visit_status": visit.get("visit_status", "WAITING_FOR_TRIAGE"),
        "triage_status": visit.get("triage_status", "PENDING"),
        "created_at": created,
        "visit_date": created[:10] if created else "",
        "visit_time": time_str,
    }


@router.get("/visits/{visit_id}")
def get_visit_route(
    visit_id: str,
    auth: AuthContext = Depends(require_role("record_officer", "admin", "nurse", "doctor")),
):
    _ = auth
    visit = visit_service.get_visit(visit_id)
    if not visit:
        raise HTTPException(
            status_code=404,
            detail=error_payload("NOT_FOUND", "Visit not found", {"visit_id": visit_id}),
        )
    return visit


# --- Dashboard ---
@router.get("/dashboard")
def dashboard_route(
    auth: AuthContext = Depends(require_role("record_officer", "admin")),
):
    """Dashboard stats, queue counts, recent visits, recent registrations."""
    from datetime import datetime

    from app.database.supabase import supabase

    _ = auth
    try:
        visits_today = visit_service.get_visits_today_count()
        waiting_triage = visit_service.get_waiting_for_triage_count()
        queue = visit_service.get_queue_counts()
        recent_visits = visit_service.get_recent_visits(limit=5)
        reg_resp = (
            supabase.table("patients")
            .select("id, first_name, last_name, registration_date")
            .order("registration_date", desc=True)
            .limit(5)
            .execute()
        )
    except Exception:
        return {
            "stats": {"visitsToday": 0, "waitingForTriage": 0, "newRegistrationsToday": 0},
            "queue": [],
            "recentVisits": [],
            "recentRegistrations": [],
        }
    reg_data = getattr(reg_resp, "data", None) or []
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    reg_today = sum(1 for r in reg_data if (r.get("registration_date") or "")[:10] == today_str)
    recent_reg = []
    for r in reg_data:
        rd = r.get("registration_date") or ""
        try:
            t = datetime.fromisoformat(rd.replace("Z", "+00:00"))
            time_str = t.strftime("%I:%M %p")
        except Exception:
            time_str = rd[11:16] if len(rd) >= 16 else rd[:10]
        recent_reg.append({
            "name": f"{(r.get('first_name') or '')} {(r.get('last_name') or '')}".strip() or "Unknown",
            "pid": r.get("id"),
            "time": time_str,
        })
    return {
        "stats": {
            "visitsToday": visits_today,
            "waitingForTriage": waiting_triage,
            "newRegistrationsToday": reg_today,
        },
        "queue": queue,
        "recentVisits": recent_visits,
        "recentRegistrations": recent_reg,
    }
