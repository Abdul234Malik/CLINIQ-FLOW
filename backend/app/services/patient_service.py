from app.database.supabase import supabase
from uuid import uuid4
from datetime import datetime, date
from app.schemas.patient import CreatePatient, UpdatePatient
from typing import Optional


def _generate_next_pid() -> str:
    """Generate next sequential PID (e.g. PID-0001, PID-0002)."""
    resp = supabase.table("patients").select("pid").not_.is_("pid", "null").execute()
    pids = [r["pid"] for r in (resp.data or []) if r.get("pid") and str(r["pid"]).startswith("PID-")]
    numbers = []
    for p in pids:
        try:
            parts = str(p).split("-", 1)
            if len(parts) == 2:
                num = int(parts[1])
                numbers.append(num)
        except ValueError:
            pass
    next_num = max(numbers, default=0) + 1
    return f"PID-{next_num:04d}"


#to auto calculate age from dob
def calculate_age(dob:date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

# the function to create patient
async def create_patient(payload: CreatePatient, current_user: dict, pid: str | None = None):
    """
    Creates a new patient record in the database.
    Args:
        payload: CreatePatient Pydantic model for validation
        current_user: dict with current logged-in officer info
    Returns:
        Inserted patient record
    """

    nin_val = None
    if payload.statutory_info and payload.statutory_info.nin:
        nin_val = payload.statutory_info.nin
    if nin_val:
        existing = supabase.table("patients").select("id").eq("nin", nin_val).execute()
        if existing.data:
            return existing.data[0]

    assigned_pid = pid if pid else _generate_next_pid()

    # Flatten nested schema for database
    data = {
        "id": str(uuid4()),  # Internal UUID (used for visits FK)
        "pid": assigned_pid,  # User-facing Patient ID (e.g. PID-0001)
        "first_name": payload.primary_bio.first_name,
        "last_name": payload.primary_bio.last_name,
        "other_names": payload.primary_bio.other_name,
        "date_of_birth": payload.primary_bio.date_of_birth.isoformat(),
        "age": calculate_age(payload.primary_bio.date_of_birth),
        "gender": payload.primary_bio.gender,
        "civil_status": payload.primary_bio.civil_status,
        "religion": payload.primary_bio.religion,
        "tribe": payload.primary_bio.tribe,
        "passport_photo_url": payload.primary_bio.passport_photo_url,
        # Contact
        "phone_number": payload.contact_info.phone_number,
        "alternative_phone": payload.contact_info.alternative_phone,
        "email": payload.contact_info.email,
        "address": payload.contact_info.address,
        "nationality": payload.contact_info.nationality,
        "state_of_origin": payload.contact_info.state_of_origin,
        "lga": payload.contact_info.lga,
        # Statutory
        "nin": payload.statutory_info.nin if payload.statutory_info else None,
        "nhis_number": payload.statutory_info.nhis_number if payload.statutory_info else None,
        "military_service_number": payload.statutory_info.military_service_number if payload.statutory_info else None,
        "education": payload.statutory_info.education if payload.statutory_info else None,
        # Emergency / Next of Kin
        "next_of_kin_name": payload.next_of_kin.full_name,
        "next_of_kin_relationship": payload.next_of_kin.relationship,
        "next_of_kin_phone": payload.next_of_kin.phone_number,
        "next_of_kin_address": payload.next_of_kin.address,
        # System fields
        "registered_by": current_user.get("id") or current_user.get("user_id") or "",
        "registration_date": datetime.utcnow().isoformat(),
    }

    # Insert into Supabase
    try:
        response = supabase.table("patients").insert(data).execute()
    except Exception as supabase_err:
        raise Exception(f"Supabase insert failed: {supabase_err}") from supabase_err

    if response.data is None or not response.data:
        raise Exception("Failed to create patient: no data returned")

    return response.data[0]

def get_total_patients_count() -> int:
    """Count total patients in the database."""
    try:
        resp = supabase.table("patients").select("id", count="exact").execute()
        return resp.count if hasattr(resp, "count") and resp.count is not None else len(resp.data or [])
    except Exception:
        return 0


def get_registrations_this_month_count() -> int:
    """Count patients registered in the current month (UTC)."""
    from datetime import datetime
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_str = month_start.isoformat() + "Z"
    try:
        resp = supabase.table("patients").select("id", count="exact").gte("registration_date", month_start_str).execute()
        return resp.count if hasattr(resp, "count") and resp.count is not None else len(resp.data or [])
    except Exception:
        return 0


#function to get patients
async def get_patients(search: Optional[str] = None, search_by: Optional[str] = None, limit: int = 100):
    """
    Returns list of patients with optional search.
    search_by: "id" | "phone" | "name" (default: name + phone + id)
    """
    query = supabase.table("patients").select("*")

    if search and search.strip():
        q = search.strip()
        if search_by == "id":
            query = query.ilike("id", f"%{q}%")
        elif search_by == "pid":
            query = query.eq("pid", q)  # Exact match; ilike with % can trigger Supabase edge errors
        elif search_by == "phone":
            query = query.or_(f"phone_number.ilike.%{q}%,alternative_phone.ilike.%{q}%")
        elif search_by == "nameDob" or search_by == "name":
            parts = q.split(maxsplit=1)
            name_part = parts[0] if parts else q
            dob_part = parts[1] if len(parts) > 1 else None
            query = query.or_(f"first_name.ilike.%{name_part}%,last_name.ilike.%{name_part}%")
            if dob_part:
                query = query.ilike("date_of_birth", f"%{dob_part}%")
        else:
            query = query.or_(
                f"first_name.ilike.%{q}%,last_name.ilike.%{q}%,phone_number.ilike.%{q}%,id.ilike.%{q}%,pid.ilike.%{q}%"
            )

    response = query.limit(limit).execute()
    return response.data

#function to get one patient
async def get_patient_by_id(patient_id: str):
    response = (
        supabase.table("patients")
        .select("*")
        .eq("id", patient_id)
        .single()
        .execute()
    )

    if response.data is None:
        raise Exception("Patient not found")

    return response.data


def get_patient_visit_stats(patient_id: str) -> dict:
    """Get previous_visits count and last_visit date for a patient."""
    try:
        visits_resp = (
            supabase.table("visits")
            .select("created_at")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .execute()
        )
        visits = visits_resp.data or []
        previous_visits = len(visits)
        last_visit = None
        if visits:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(visits[0]["created_at"].replace("Z", "+00:00"))
                last_visit = dt.strftime("%b %d, %Y")
            except Exception:
                last_visit = str(visits[0].get("created_at", ""))[:10]
        return {"previous_visits": previous_visits, "last_visit": last_visit or "—"}
    except Exception:
        return {"previous_visits": 0, "last_visit": "—"}


def get_visit_stats_bulk(patient_ids: list[str]) -> dict[str, dict]:
    """Get previous_visits and last_visit for many patients in one query (avoids N+1)."""
    patient_ids = [x for x in patient_ids if x]
    if not patient_ids:
        return {}
    try:
        visits_resp = (
            supabase.table("visits")
            .select("patient_id, created_at")
            .in_("patient_id", patient_ids)
            .order("created_at", desc=True)
            .execute()
        )
        visits = visits_resp.data or []
        # Group by patient_id: { pid: [(created_at, ...), ...] }
        by_patient: dict[str, list] = {}
        for v in visits:
            pid = v.get("patient_id")
            if pid:
                by_patient.setdefault(pid, []).append(v)
        # Build stats
        from datetime import datetime
        result = {}
        for pid in patient_ids:
            pat_visits = by_patient.get(pid, [])
            last_visit = None
            if pat_visits:
                try:
                    dt = datetime.fromisoformat(pat_visits[0]["created_at"].replace("Z", "+00:00"))
                    last_visit = dt.strftime("%b %d, %Y")
                except Exception:
                    last_visit = str(pat_visits[0].get("created_at", ""))[:10]
            result[pid] = {"previous_visits": len(pat_visits), "last_visit": last_visit or "—"}
        return result
    except Exception:
        return {pid: {"previous_visits": 0, "last_visit": "—"} for pid in patient_ids}

#function to update patient data
async def update_patient(patient_id: str, payload: UpdatePatient):
    update_data = payload.dict(exclude_unset=True)

    response = (
        supabase.table("patients")
        .update(update_data)
        .eq("id", patient_id)
        .execute()
    )

    if response.data is None:
        raise Exception("Failed to update patient")

    return response.data[0]