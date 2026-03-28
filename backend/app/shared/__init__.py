"""Shared models and schemas for CLINIQ-FLOW backend and AI engine.

Single source of truth for data contracts across services.
"""

from .clinical_schema import (
    Severity,
    ConfidenceLevel,
    SOAPSection,
    ExtractionMethod,
    Symptom,
    VitalSign,
    PatientDemographics,
    AllergyRecord,
    MedicalHistory,
    ClinicalFlag,
    StructuredClinicalData,
    SOAPNote,
    ValidationResult,
    NLPRequest,
    NLPResponse,
)
from .dose import DoseCheckRequest, DoseCheckResponse
from .intake import IntakeRequest
from .triage import TriageResult
from .patient import (
    BioData,
    ContactInfo,
    StatutoryInfo,
    NextOfKin,
    MedicalAssignment,
    CreatePatient,
    UpdatePatient,
)

__all__ = [
    # clinical_schema
    "Severity",
    "ConfidenceLevel",
    "SOAPSection",
    "ExtractionMethod",
    "Symptom",
    "VitalSign",
    "PatientDemographics",
    "AllergyRecord",
    "MedicalHistory",
    "ClinicalFlag",
    "StructuredClinicalData",
    "SOAPNote",
    "ValidationResult",
    "NLPRequest",
    "NLPResponse",
    # dose
    "DoseCheckRequest",
    "DoseCheckResponse",
    # intake
    "IntakeRequest",
    # triage
    "TriageResult",
    # patient
    "BioData",
    "ContactInfo",
    "StatutoryInfo",
    "NextOfKin",
    "MedicalAssignment",
    "CreatePatient",
    "UpdatePatient",
]
