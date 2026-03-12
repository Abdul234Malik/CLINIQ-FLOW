# Patient's Schema
from pydantic import BaseModel, Field, EmailStr
from datetime import date
from typing import Optional
from uuid import UUID

# pydantic for bio-data
class BioData(BaseModel):
    first_name: str = Field(..., min_length=2, example="Ayodele")
    last_name: str = Field(..., min_length=2, example="Eze")
    other_name: Optional[str] = None
    date_of_birth: date
    gender: str
    civil_status: Optional[str] = None
    religion: Optional[str] = None
    tribe: Optional[str] = None
    passport_photo_url: Optional[str] = None

#pydantic for contact info
class ContactInfo(BaseModel):
    phone_number: str = Field(..., min_length=7, max_length=20)
    alternative_phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: str
    nationality: Optional[str] = None
    state_of_origin: Optional[str] = None
    lga: Optional[str] = None

#pydantic model for statutory info
class StatutoryInfo(BaseModel):
    nin: Optional[str] = None
    nhis_number: Optional[str] = None
    military_service_number: Optional[str] = None
    education: Optional[str] = None

#pydantic model for emrgency contact
class NextOfKin(BaseModel):
    full_name: str
    relationship: str
    phone_number: str
    address: Optional[str] = None

#pydantic model for doctor's incharge
class MedicalAssignment(BaseModel):
    doctor_in_charge: Optional[UUID] = None

# create patient pydantic
class CreatePatient(BaseModel):
    primary_bio: BioData
    contact_info: ContactInfo
    statutory_info: Optional[StatutoryInfo] = None
    next_of_kin: NextOfKin
    medical_assignment: Optional[MedicalAssignment] = None

# update patient pydantic
class UpdatePatient(BaseModel):
    # All optional, so just the fields that need update are edited
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    other_names: Optional[str] = None
    phone_number: Optional[str] = None
    alternative_phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    nationality: Optional[str] = None
    state_of_origin: Optional[str] = None
    lga: Optional[str] = None
    civil_status: Optional[str] = None
    religion: Optional[str] = None
    tribe: Optional[str] = None
    next_of_kin_name: Optional[str] = None
    next_of_kin_relationship: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    next_of_kin_address: Optional[str] = None