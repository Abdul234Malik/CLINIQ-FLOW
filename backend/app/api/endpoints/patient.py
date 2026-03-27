from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from app.schemas.patient import CreatePatient, UpdatePatient
from app.services import patient_service
from app.core.dependencies import require_role


router = APIRouter()

#post a newly registered patient to the database 
@router.post("/", description="Register a new patient")
async def create_patient(
    payload: CreatePatient,
    current_user=Depends(require_role("record_officer"))
):
    try:
        patient = await patient_service.create_patient(payload, current_user)
        return patient
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

# get patients from the db or search patient
@router.get("/", description="Get all patients or search")
async def get_patients(
    search: Optional[str] = None,
    current_user=Depends(require_role("record_officer"))
):
    patients = await patient_service.get_patients(search)
    return patients


#get one patient by PID
@router.get("/{patient_id}", description="Get a single patient by PID")
async def get_patient(
    patient_id: str,
    current_user=Depends(require_role("record_officer"))
):
    try:
        patient = await patient_service.get_patient_by_id(patient_id)
        return patient
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    

# patch patient to edit/update info
@router.patch("/{patient_id}", description="Update patient information")
async def update_patient(
    patient_id: str,
    payload: UpdatePatient,
    current_user=Depends(require_role("record_officer"))
):
    try:
        updated_patient = await patient_service.update_patient(patient_id, payload)
        return updated_patient
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
