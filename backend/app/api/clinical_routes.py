"""Shared clinical endpoints.

Provides general workflow APIs used across roles:
patient/visit lookup, latest intake retrieval, and doctor conversation summary.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator

from app.models.clinical_schema import VitalSign
from app.services.nlp.soap_formatter import SOAPFormatter
from app.services.nlp.symptom_extractor import SymptomExtractor
from app.services import triage_service
from app.services.nlp.vitals_urgency import default_urgency_stub
from app.services.nlp.validators import ClinicalValidator
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.errors import error_payload
from app.utils.pydantic_compat import model_to_dict
from app.database.supabase import supabase
from app.services import patient_service
from app.services import visit_service
from app.utils.storage import add_audit_log
from app.utils.storage import create_patient as local_create_patient
from app.utils.storage import create_doctor_conversation
from app.utils.storage import create_visit as local_create_visit
from app.utils.storage import get_patient as local_get_patient
from app.utils.storage import get_latest_doctor_conversation
from app.utils.storage import get_latest_intake

router = APIRouter(tags=["Clinical"])


def _get_visit_safe(visit_id: str):
    """Get visit from Supabase. Returns None if not found or error."""
    try:
        return visit_service.get_visit(visit_id)
    except Exception:
        return None


class PatientCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=2)
    date_of_birth: str | None = None
    gender: str | None = None
    phone: str | None = None


class VisitCreateRequest(BaseModel):
    patient_id: str = Field(...)
    visit_status: str = Field(default="open")


class DoctorConversationRequest(BaseModel):
    transcript: str = Field(..., min_length=5)
    patient_age: str | None = None  # Accepts str or coerced from int
    patient_sex: str | None = None
    audio_reference: str | None = None
    triage_vitals: dict | None = None  # From nurse triage: temperature, bpSystolic, bpDiastolic, heartRate, respiratoryRate, weight, height, bmi

    @validator("patient_age", "patient_sex", pre=True)
    def coerce_to_str(cls, v):
        if v is None or v == "":
            return None
        return str(v)


def _triage_vitals_to_vital_signs(vitals: dict | None) -> list:
    """Convert triage vitals dict to VitalSign list for SOAP Objective."""
    if not vitals:
        return []
    out = []
    v = vitals
    if v.get("temperature") is not None:
        t = float(v["temperature"]) if isinstance(v["temperature"], (int, float)) else float(v["temperature"] or 0)
        abnormal = t < 36.0 or t > 37.5
        out.append(VitalSign(name="temperature", value=str(v["temperature"]), unit="°C", normal_range="36-37.5", is_abnormal=abnormal))
    if v.get("bpSystolic") is not None and v.get("bpDiastolic") is not None:
        out.append(VitalSign(name="blood_pressure", value=f"{v['bpSystolic']}/{v['bpDiastolic']}", unit="mmHg", normal_range="120/80"))
    elif v.get("bpSystolic") is not None:
        out.append(VitalSign(name="blood_pressure_systolic", value=str(v["bpSystolic"]), unit="mmHg", normal_range="90-120"))
    elif v.get("bpDiastolic") is not None:
        out.append(VitalSign(name="blood_pressure_diastolic", value=str(v["bpDiastolic"]), unit="mmHg", normal_range="60-80"))
    if v.get("heartRate") is not None:
        hr = int(v["heartRate"]) if isinstance(v["heartRate"], (int, float)) else int(v["heartRate"] or 0)
        abnormal = hr < 60 or hr > 100
        out.append(VitalSign(name="heart_rate", value=str(v["heartRate"]), unit="bpm", normal_range="60-100", is_abnormal=abnormal))
    if v.get("respiratoryRate") is not None:
        out.append(VitalSign(name="respiratory_rate", value=str(v["respiratoryRate"]), unit="/min", normal_range="12-20"))
    if v.get("oxygenSaturation") is not None:
        out.append(VitalSign(name="oxygen_saturation", value=str(v["oxygenSaturation"]), unit="%", normal_range="95-100"))
    return out


@router.post("/patients")
def create_patient_route(
    payload: PatientCreateRequest,
    auth: AuthContext = Depends(require_role("record_officer", "nurse", "doctor", "admin")),
):
    """Create patient in Supabase. Minimal schema (matches record-officer quick registration)."""
    if supabase is None:
        row = local_create_patient(
            patient_id=str(uuid.uuid4()),
            full_name=payload.full_name.strip(),
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            phone=payload.phone,
        )
        add_audit_log(
            audit_id=str(uuid.uuid4()),
            actor_role=auth.role,
            action="create_patient",
            entity_type="patient",
            entity_id=row.get("id", ""),
            metadata={"full_name": payload.full_name},
        )
        return {**row, "created_at": row.get("created_at", "")}

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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", f"Failed to create patient: {e}", None),
        ) from e
    add_audit_log(
        audit_id=str(uuid.uuid4()),
        actor_role=auth.role,
        action="create_patient",
        entity_type="patient",
        entity_id=patient_id,
        metadata={"full_name": payload.full_name},
    )
    return {**data, "created_at": ""}


@router.get("/patients/{patient_id}")
async def get_patient_route(
    patient_id: str,
    auth: AuthContext = Depends(require_role("record_officer", "nurse", "doctor", "admin")),
):
    _ = auth
    if supabase is None:
        patient = local_get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Patient not found", {"patient_id": patient_id}))
        return patient
    try:
        patient = await patient_service.get_patient_by_id(patient_id)
    except Exception:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Patient not found", {"patient_id": patient_id}))
    return patient


@router.post("/visits")
async def create_visit_route(
    payload: VisitCreateRequest,
    auth: AuthContext = Depends(require_role("record_officer", "nurse", "doctor", "admin")),
):
    """Create visit in Supabase. Status: WAITING_FOR_TRIAGE."""
    if supabase is None:
        patient = local_get_patient(payload.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Patient not found", {"patient_id": payload.patient_id}))
        visit = local_create_visit(visit_id=str(uuid.uuid4()), patient_id=payload.patient_id, visit_status=payload.visit_status or "open")
        add_audit_log(
            audit_id=str(uuid.uuid4()),
            actor_role=auth.role,
            action="create_visit",
            entity_type="visit",
            entity_id=visit.get("id", ""),
            metadata={"patient_id": payload.patient_id},
        )
        return visit
    try:
        patient = await patient_service.get_patient_by_id(payload.patient_id)
    except Exception:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Patient not found", {"patient_id": payload.patient_id}))
    try:
        visit = visit_service.create_visit(
            patient_id=payload.patient_id,
            created_by=auth.user_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=error_payload("INTERNAL_ERROR", str(e), None),
        ) from e
    add_audit_log(
        audit_id=str(uuid.uuid4()),
        actor_role=auth.role,
        action="create_visit",
        entity_type="visit",
        entity_id=visit.get("id", ""),
        metadata={"patient_id": payload.patient_id},
    )
    return visit


@router.get("/visits/{visit_id}")
def get_visit_route(
    visit_id: str,
    auth: AuthContext = Depends(require_role("record_officer", "nurse", "doctor", "admin")),
):
    _ = auth
    visit = _get_visit_safe(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Visit not found", {"visit_id": visit_id}))
    return visit


@router.get("/visits/{visit_id}/latest-intake")
def latest_intake_route(
    visit_id: str,
    auth: AuthContext = Depends(require_role("nurse", "doctor", "admin")),
):
    _ = auth
    row = get_latest_intake(visit_id)
    if not row:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "No intake found for visit", {"visit_id": visit_id}))

    for field in ("structured_json", "red_flags_json", "summary_json"):
        raw = row.get(field)
        if isinstance(raw, str):
            try:
                row[field] = json.loads(raw)
            except Exception:
                pass
    return row


@router.post("/visits/{visit_id}/doctor-conversation")
def doctor_conversation_route(
    visit_id: str,
    payload: DoctorConversationRequest,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    visit = _get_visit_safe(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "Visit not found", {"visit_id": visit_id}))

    extractor = SymptomExtractor()
    formatter = SOAPFormatter()
    validator = ClinicalValidator()

    structured_data, _ = extractor.extract(
        transcript=payload.transcript,
        session_id=f"doctor-{visit_id}-{uuid.uuid4()}",
        patient_age=payload.patient_age,
        patient_sex=payload.patient_sex,
    )

    # Inject triage vitals into SOAP Objective (nurse-recorded vitals)
    triage_vitals = payload.triage_vitals
    if not triage_vitals:
        # Fallback: fetch vitals from triage record in database
        triage_row = triage_service.get_latest_triage_for_visit(visit_id)
        if triage_row and triage_row.get("vitals"):
            triage_vitals = triage_row["vitals"]
    if triage_vitals:
        triage_signs = _triage_vitals_to_vital_signs(triage_vitals)
        if triage_signs:
            def _key(vs):
                return vs.name.lower().replace(" ", "_")
            existing = {_key(vs): vs for vs in structured_data.vital_signs}
            for vs in triage_signs:
                existing[_key(vs)] = vs  # Triage overwrites transcript
            structured_data.vital_signs = list(existing.values())
        v = triage_vitals
        w = v.get("weight") or v.get("weight_kg")
        h = v.get("height") or v.get("height_cm")
        if w is not None:
            try:
                structured_data.demographics.weight_kg = float(w)
            except (TypeError, ValueError):
                pass
        if h is not None:
            try:
                structured_data.demographics.height_cm = float(h)
            except (TypeError, ValueError):
                pass
        if v.get("bmi") is not None:
            try:
                structured_data.demographics.bmi = float(v["bmi"])
            except (TypeError, ValueError):
                pass
        # Remove from missing_fields if we now have them
        for key in ("weight_kg", "height_cm", "vital_signs"):
            if key in structured_data.missing_fields:
                if (key == "vital_signs" and triage_signs) or (key == "weight_kg" and structured_data.demographics.weight_kg) or (key == "height_cm" and structured_data.demographics.height_cm):
                    structured_data.missing_fields = [m for m in structured_data.missing_fields if m != key]

    soap_note = formatter.format(structured_data)
    validation = validator.validate_all(structured_data, soap_note)
    urgency = default_urgency_stub()

    conversation_id = str(uuid.uuid4())
    stored = create_doctor_conversation(
        conversation_id=conversation_id,
        visit_id=visit_id,
        transcript=payload.transcript,
        structured_json=dict(model_to_dict(structured_data, mode="json")),
        soap_json={
            "subjective": soap_note.subjective,
            "objective": soap_note.objective,
            "assessment": soap_note.assessment,
            "plan": soap_note.plan,
            "disclaimer": soap_note.disclaimer,
        },
        urgency_json=urgency,
        validation_json=dict(model_to_dict(validation, mode="json")),
        audio_reference=payload.audio_reference,
    )
    add_audit_log(
        audit_id=str(uuid.uuid4()),
        actor_role=auth.role,
        action="doctor_conversation_summary",
        entity_type="visit",
        entity_id=visit_id,
        metadata={"conversation_id": conversation_id},
    )

    return {
        "visit_id": visit_id,
        "conversation_id": conversation_id,
        "structured_data": structured_data,
        "soap_note": soap_note,
        "validation": validation,
        "urgency": urgency,
        "stored": stored,
    }


@router.get("/visits/{visit_id}/doctor-conversation/latest")
def latest_doctor_conversation_route(
    visit_id: str,
    auth: AuthContext = Depends(require_role("doctor", "admin")),
):
    _ = auth
    row = get_latest_doctor_conversation(visit_id)
    if not row:
        raise HTTPException(status_code=404, detail=error_payload("NOT_FOUND", "No doctor conversation found", {"visit_id": visit_id}))
    for field in ("structured_json", "soap_json", "urgency_json", "validation_json"):
        raw = row.get(field)
        if isinstance(raw, str):
            try:
                row[field] = json.loads(raw)
            except Exception:
                pass
    return row
