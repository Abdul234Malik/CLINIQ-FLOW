from app.api.endpoints import patient
from fastapi import APIRouter

api_router = APIRouter()

api_router.include_router(
    patient.router,
    prefix="/patients",
    tags=["Patients"]
)