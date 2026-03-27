"""Admin-facing endpoints.

These routes expose system-wide monitoring information such as metrics,
sync status, and audit logs. They are protected with admin role checks.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Depends

from app.services.sync.supabase_sync import SupabaseSyncService
from app.services import patient_service
from app.services import visit_service
from app.utils.auth import AuthContext
from app.utils.auth import require_role
from app.utils.storage import get_metrics
from app.utils.storage import list_audit_logs
from pydantic import BaseModel
# Legacy imports kept for review:
# from pydantic import BaseModel, EmailStr
# from supabase import create_client, Client
# Commented out because they made admin startup depend on optional packages
# and config even for routes like /health and test imports.
from app.dependency.dependencies import verify_admin
from dotenv import load_dotenv

load_dotenv()


router = APIRouter()


class AdminCreateUserRequest(BaseModel):
    email: str
    password: str | None = None
    role: str | None = None
    display_name: str | None = None


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
# Legacy eager client kept for review:
# supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
# Commented out because it crashed module import when Supabase env vars or the
# package were unavailable, blocking the whole app from starting.


def _get_supabase_admin():
    try:
        from supabase import create_client
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Supabase admin client is not available") from exc

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase admin client is not configured")

    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@router.post("/invite-user")
async def invite_user(
    request: AdminCreateUserRequest, admin_user: AuthContext = Depends(verify_admin)
):
    try:
        supabase_admin = _get_supabase_admin()
        # 1. Using inviteUserByEmail triggers the Supabase 'Invite' email template automatically
        user_metadata = {
            "role": request.role,
            "created_by_admin": True,
            "needs_password_update": True,
            "created_by": admin_user.email,
        }
        if request.display_name:
            user_metadata["display_name"] = request.display_name
            user_metadata["name"] = request.display_name
        supabase_admin.auth.admin.create_user(
            {
                "email": request.email,
                "password": request.password,
                "email_confirm": True,
                "user_metadata": user_metadata,
            }
        )
        return {"message": f"User created by admin: {admin_user.email}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users")
async def list_users(admin_user: AuthContext = Depends(verify_admin)):
    """Admin-only: list users exposing only `display_name` and `role` from metadata."""
    try:
        supabase_admin = _get_supabase_admin()
        result = supabase_admin.auth.admin.list_users()

        # Normalize the returned users list from different SDK response shapes
        if isinstance(result, dict):
            raw_users = result.get("users") or result.get("data") or []
        elif hasattr(result, "data"):
            raw_users = result.data or []
        else:
            raw_users = result or []

        def to_dict(obj):
            if obj is None:
                return {}
            if isinstance(obj, dict):
                return obj
            # pydantic/BaseModel style
            if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
                try:
                    return obj.dict()
                except Exception:
                    pass
            # fallback to __dict__
            if hasattr(obj, "__dict__"):
                try:
                    return obj.__dict__
                except Exception:
                    pass
            return {}

        users = []
        for u in raw_users:
            u_dict = to_dict(u)
            metadata = to_dict(
                u_dict.get("user_metadata")
                or u_dict.get("raw_user_meta_data")
                or u_dict.get("raw_user_metadata")
            )
            display_name = metadata.get("display_name") or metadata.get("name")
            users.append(
                {
                    "id": u_dict.get("id"),
                    "email": u_dict.get("email"),
                    "display_name": display_name,
                    "name": display_name,
                    "role": metadata.get("role"),
                }
            )
        return users
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/metrics")
def admin_metrics(auth: AuthContext = Depends(require_role("admin"))):
    _ = auth
    return get_metrics()


@router.get("/stats")
def admin_stats(auth: AuthContext = Depends(require_role("admin"))):
    """Dashboard stats: total patients, visits today, new registrations this month, doctor queue."""
    _ = auth
    try:
        total_patients = patient_service.get_total_patients_count()
        visits_today = visit_service.get_visits_today_count()
        new_registrations = patient_service.get_registrations_this_month_count()
        doctor_queue = visit_service.get_waiting_for_doctor_count()
        return {
            "totalPatients": total_patients,
            "visitsToday": visits_today,
            "newRegistrationsThisMonth": new_registrations,
            "doctorQueue": doctor_queue,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/status")
def sync_status(auth: AuthContext = Depends(require_role("admin"))):
    _ = auth
    return SupabaseSyncService().status()


@router.post("/sync/run")
def run_sync(auth: AuthContext = Depends(require_role("admin"))):
    _ = auth
    return SupabaseSyncService().sync_once()


@router.get("/logs")
def admin_logs(limit: int = 100, auth: AuthContext = Depends(require_role("admin"))):
    _ = auth
    return {"items": list_audit_logs(limit=limit)}
