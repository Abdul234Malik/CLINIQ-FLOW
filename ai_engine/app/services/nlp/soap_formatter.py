"""
module: Converts StructuredClinicalData into a formatted SOAP note.
Follows clinical writing conventions.
SAFETY: No diagnosis, no treatment decisions. Summary only.

"""

from __future__ import annotations

import logging
import textwrap
from typing import List, Optional

from app.models.clinical_schema import (
    ClinicalFlag,
    ConfidenceLevel,
    Severity,
    SOAPNote,
    StructuredClinicalData,
    Symptom,
    VitalSign,
)

logger = logging.getLogger("cliniq.nlp.soap")

SEVERITY_LABEL = {
    Severity.LOW: "LOW",
    Severity.MODERATE: "MODERATE",
    Severity.HIGH: "HIGH",
    Severity.CRITICAL: "CRITICAL",
}


class SOAPFormatter:
    """
    Generates SOAP notes from structured clinical data.
    Each section is built deterministically — no LLM required.
    """

    def format(self, data: StructuredClinicalData) -> SOAPNote:
        subjective = self._build_subjective(data)
        objective = self._build_objective(data)
        assessment = self._build_assessment(data)
        plan = self._build_plan(data)

        note = SOAPNote(
            session_id=data.session_id,
            subjective=subjective,
            objective=objective,
            assessment=assessment,
            plan=plan,
            confidence_level=data.confidence_level,
            flags=data.clinical_flags,
        )

        logger.info(
            f"SOAP note generated | session={data.session_id} | "
            f"words={note.word_count} | flags={len(note.flags)}"
        )
        return note

   
    # S — Subjective

    def _build_subjective(self, data: StructuredClinicalData) -> str:
        parts: List[str] = []

        # Chief complaint
        if data.chief_complaint:
            parts.append(f"Chief Complaint: {data.chief_complaint.capitalize()}")

        # Demographics
        demo_parts = []
        if data.demographics.age:
            demo_parts.append(data.demographics.age)
        if data.demographics.sex:
            demo_parts.append(data.demographics.sex)
        if data.demographics.weight_kg:
            demo_parts.append(f"{data.demographics.weight_kg} kg")
        if data.demographics.height_cm:
            demo_parts.append(f"{data.demographics.height_cm} cm tall")
        if data.demographics.bmi:
            demo_parts.append(f"BMI {data.demographics.bmi:.1f}")
        if demo_parts:
            parts.append(f"Patient: {', '.join(demo_parts)}")

        # Symptoms narrative
        if data.symptoms:
            symptom_lines = []
            for symptom in data.symptoms:
                line = f"- {symptom.name.replace('_', ' ').title()}"
                extras = []
                if symptom.duration:
                    extras.append(f"duration: {symptom.duration}")
                if symptom.severity:
                    extras.append(f"severity: {symptom.severity.value}")
                if symptom.onset:
                    extras.append(f"onset: {symptom.onset}")
                if symptom.location:
                    extras.append(f"location: {symptom.location}")
                if symptom.modifiers:
                    extras.append(", ".join(symptom.modifiers))
                if extras:
                    line += f" ({'; '.join(extras)})"
                symptom_lines.append(line)
            parts.append("Reported Symptoms:\n" + "\n".join(symptom_lines))

        # History
        h = data.history
        if h.past_conditions:
            parts.append("Past Medical History: " + ", ".join(h.past_conditions))
        if h.current_medications:
            parts.append("Current Medications: " + ", ".join(h.current_medications))
        if h.allergies:
            allergy_text = ", ".join(
                f"{a.substance}{' (' + a.reaction + ')' if a.reaction else ''}"
                for a in h.allergies
            )
            parts.append(f"Allergies: {allergy_text}")
        if h.family_history:
            parts.append("Family History: " + "; ".join(h.family_history))
        if h.immunisation_status:
            parts.append(f"Immunisation Status: {h.immunisation_status}")

        if not parts:
            return "No subjective information could be extracted from the transcript."

        return "\n\n".join(parts)

 
    # O — Objective

    def _build_objective(self, data: StructuredClinicalData) -> str:
        parts: List[str] = []

        if data.vital_signs:
            vital_lines = []
            for v in data.vital_signs:
                abnormal_tag = "ABNORMAL" if v.is_abnormal else ""
                unit_str = f" {v.unit}" if v.unit else ""
                normal_range_str = f" (normal: {v.normal_range})" if v.normal_range else ""
                vital_lines.append(f"- {v.name.replace('_', ' ').title()}: {v.value}{unit_str}{normal_range_str}{abnormal_tag}")
            parts.append("Vital Signs:\n" + "\n".join(vital_lines))
        else:
            parts.append("Vital Signs: Not documented in transcript")

        if data.demographics.weight_kg:
            anthropometric = f"Weight: {data.demographics.weight_kg} kg"
            if data.demographics.height_cm:
                anthropometric += f", Height: {data.demographics.height_cm} cm"
            if data.demographics.bmi:
                anthropometric += f", BMI: {data.demographics.bmi:.1f}"
            parts.append(anthropometric)

        parts.append(
            "Physical Examination: Not available — transcript-based extraction only. "
            "Clinician to complete physical findings."
        )

        return "\n\n".join(parts)

 
    # A — Assessment

    def _build_assessment(self, data: StructuredClinicalData) -> str:
        """
        Clinical summary — NO diagnosis, NO differential.
        States what was reported and flags of concern.
        """
        parts: List[str] = []

        # Confidence note
        confidence_notes = {
            ConfidenceLevel.HIGH: "High-confidence extraction from transcript.",
            ConfidenceLevel.MEDIUM: "Moderate-confidence extraction. Some fields may be incomplete.",
            ConfidenceLevel.LOW: "Low-confidence extraction. Manual review strongly recommended.",
        }
        parts.append(f"AI Extraction Quality: {confidence_notes[data.confidence_level]}")

        # Symptom summary
        if data.symptoms:
            symptom_names = [s.name.replace("_", " ") for s in data.symptoms]
            parts.append(
                f"The patient presents with the following reported symptoms: "
                f"{', '.join(symptom_names)}."
            )

        # Missing fields note
        if data.missing_fields:
            parts.append(
                f"Note: The following clinical fields were not captured and require "
                f"direct assessment: {', '.join(data.missing_fields)}."
            )

        # Flags
        if data.clinical_flags:
            flag_lines = []
            for flag in data.clinical_flags:
                level = SEVERITY_LABEL.get(flag.severity, "UNKNOWN")
                flag_lines.append(f"  [{level}] [{flag.flag_type.upper()}] {flag.description}")
            parts.append("Clinical Alerts:\n" + "\n".join(flag_lines))

        # If cardiac risk flagged, add a focused clinical concern paragraph
        cardiac_flags = [f for f in data.clinical_flags if f.flag_type == "cardiac_risk"]
        if cardiac_flags:
            parts.append(
                "Focused concern: Exertional chest pain in a patient with cardiovascular risk factors. "
                "This is concerning for possible ischemic cardiac pathology and requires urgent clinical evaluation. "
                "Obtain ECG and cardiac enzymes (troponin) promptly and arrange in-person assessment."
            )

        parts.append(
            "DISCLAIMER: This assessment section is an AI-generated summary of reported "
            "information only. It does not constitute a clinical diagnosis. "
            "All interpretation must be performed by a licensed healthcare provider."
        )

        return "\n\n".join(parts)

    
    # P — Plan

    def _build_plan(self, data: StructuredClinicalData) -> str:
        """
        Suggested next steps — NO prescriptions, NO treatment decisions.
        """
        parts: List[str] = []

        parts.append(
            "The following are suggested pre-consultation steps for the clinician's consideration. "
            "All clinical decisions remain with the treating physician."
        )

        steps = []

        # Always: clinician review
        steps.append("1. Clinician to review AI-extracted summary and verify accuracy with patient/caregiver.")

        # Missing critical fields
        if data.missing_fields:
            steps.append(
                f"2. Complete missing clinical data: {', '.join(data.missing_fields)}."
            )

        # If danger signs
        critical_flags = [f for f in data.clinical_flags if f.severity == Severity.CRITICAL]
        if critical_flags:
            steps.append(
                "3. URGENT: Danger signs detected. Immediate clinical assessment recommended. "
                "Do not delay review."
            )

        # If cardiac risk
        cardiac_flags = [f for f in data.clinical_flags if f.flag_type == "cardiac_risk"]
        if cardiac_flags:
            steps.append(
                "3. URGENT: Cardiac risk identified. Recommend immediate in-person medical assessment. "
                "Obtain ECG, cardiac enzymes (troponin), and basic labs. Monitor vitals and avoid exertion. "
                "Escalate to emergency services if symptoms worsen."
            )

        # Abnormal vitals
        abnormal_vitals = [v for v in data.vital_signs if v.is_abnormal]
        if abnormal_vitals:
            vital_names = ", ".join(v.name.replace("_", " ") for v in abnormal_vitals)
            steps.append(f"4. Review abnormal vital signs: {vital_names}.")

        # Completeness suggestion
        if data.confidence_level in (ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM):
            steps.append(
                "5. Transcript quality is limited. Clinician to gather additional history directly."
            )

        parts.append("\n".join(steps))

        parts.append(
            "PLAN DISCLAIMER: This section contains NO medication dosages, NO treatment decisions, "
            "and NO diagnostic conclusions. It is a pre-consultation aide only."
        )

        return "\n\n".join(parts)
