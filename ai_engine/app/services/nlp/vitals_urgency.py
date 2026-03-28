"""
Vitals-based urgency scoring for nurse triage form.
Takes numeric vitals (temp, BP, HR, RR, etc.) and returns emergency | urgent | normal.
Supports rule-based (deterministic) and optional LLM fallback when OpenAI is configured.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

# Optional: use OpenAI for nuanced assessment when available
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger("cliniq.vitals_urgency")


@dataclass
class VitalsUrgencyResult:
    urgency_level: str  # emergency | urgent | normal
    reasons: list[str]
    score: int  # 0-100


def _parse_age_years(age_str: str | None) -> int | None:
    """Parse age string like '45 years', '8 months', '5' to approximate years."""
    if not age_str or not str(age_str).strip():
        return None
    s = str(age_str).strip().lower()
    # "45 years" -> 45
    m = re.search(r"(\d+)\s*years?", s)
    if m:
        return int(m.group(1))
    # "8 months" -> 0
    if "month" in s or "week" in s:
        m = re.search(r"(\d+)", s)
        return 0 if m else None
    # "5" -> 5
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _is_pediatric(age_years: int | None) -> bool:
    return age_years is not None and age_years < 18


def _rule_based_urgency(
    temperature: float | None,
    bp_systolic: float | None,
    bp_diastolic: float | None,
    heart_rate: float | None,
    respiratory_rate: float | None,
    oxygen_saturation: float | None,
    age_years: int | None,
) -> VitalsUrgencyResult:
    """
    Rule-based urgency from vital signs.
    Uses standard clinical reference ranges for adults; pediatric thresholds are more conservative.
    """
    reasons: list[str] = []
    score = 0
    is_ped = _is_pediatric(age_years)

    # Temperature (°C) — check hypothermia first (most critical), then fever bands
    if temperature is not None:
        if temperature < 35.0:
            score = max(score, 85)
            reasons.append(f"Hypothermia ({temperature}°C)")
        elif temperature >= 40.0:
            score = max(score, 95)
            reasons.append(f"High fever ({temperature}°C) - emergency")
        elif temperature >= 39.0:
            score = max(score, 75)
            reasons.append(f"Fever ({temperature}°C)")
        elif temperature >= 38.0 or temperature < 36.0:
            score = max(score, 50)
            reasons.append(f"Abnormal temperature ({temperature}°C)")

    # Blood pressure (mmHg)
    if bp_systolic is not None and bp_diastolic is not None:
        if bp_systolic >= 180 or bp_diastolic >= 120:
            score = max(score, 90)
            reasons.append(f"Severe hypertension ({bp_systolic}/{bp_diastolic})")
        elif bp_systolic >= 160 or bp_diastolic >= 100:
            score = max(score, 65)
            reasons.append(f"Elevated BP ({bp_systolic}/{bp_diastolic})")
        elif bp_systolic < 90 or bp_diastolic < 60:
            score = max(score, 80)
            reasons.append(f"Low BP ({bp_systolic}/{bp_diastolic}) - may indicate shock")
        elif bp_systolic < 100:
            score = max(score, 55)
            reasons.append(f"Low-normal BP ({bp_systolic}/{bp_diastolic})")

    # Heart rate (bpm) - adult norms ~60-100
    if heart_rate is not None:
        if is_ped:
            if heart_rate > 160 or heart_rate < 80:
                score = max(score, 85)
                reasons.append(f"Abnormal pediatric heart rate ({heart_rate} bpm)")
            elif heart_rate > 140 or heart_rate < 90:
                score = max(score, 60)
                reasons.append(f"Elevated pediatric HR ({heart_rate} bpm)")
        else:
            if heart_rate >= 140 or heart_rate < 50:
                score = max(score, 85)
                reasons.append(f"Critical heart rate ({heart_rate} bpm)")
            elif heart_rate >= 120 or heart_rate < 55:
                score = max(score, 65)
                reasons.append(f"Abnormal heart rate ({heart_rate} bpm)")

    # Respiratory rate
    if respiratory_rate is not None:
        if respiratory_rate >= 30 or respiratory_rate < 8:
            score = max(score, 90)
            reasons.append(f"Critical respiratory rate ({respiratory_rate}/min)")
        elif respiratory_rate >= 24 or respiratory_rate < 10:
            score = max(score, 60)
            reasons.append(f"Abnormal respiratory rate ({respiratory_rate}/min)")

    # Oxygen saturation
    if oxygen_saturation is not None:
        if oxygen_saturation < 90:
            score = max(score, 95)
            reasons.append(f"Low SpO2 ({oxygen_saturation}%) - emergency")
        elif oxygen_saturation < 94:
            score = max(score, 75)
            reasons.append(f"Reduced SpO2 ({oxygen_saturation}%)")

    # Determine level
    if score >= 85:
        level = "emergency"
    elif score >= 55:
        level = "urgent"
    else:
        level = "normal"
        if not reasons:
            reasons.append("Vitals within normal range")

    return VitalsUrgencyResult(
        urgency_level=level,
        reasons=reasons,
        score=min(score, 100),
    )


def _llm_urgency(
    temperature: float | None,
    bp_systolic: float | None,
    bp_diastolic: float | None,
    heart_rate: float | None,
    respiratory_rate: float | None,
    oxygen_saturation: float | None,
    weight_kg: float | None,
    height_cm: float | None,
    patient_age: str | None,
    patient_sex: str | None,
) -> VitalsUrgencyResult | None:
    """
    Use OpenAI to assess urgency from vitals when API key is available.
    Returns None if LLM is not configured or request fails.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or OpenAI is None:
        logger.debug("LLM urgency skip: OPENAI_API_KEY not set or OpenAI import failed")
        return None

    vitals_desc = []
    if temperature is not None:
        vitals_desc.append(f"Temperature: {temperature}°C")
    if bp_systolic is not None and bp_diastolic is not None:
        vitals_desc.append(f"Blood pressure: {bp_systolic}/{bp_diastolic} mmHg")
    if heart_rate is not None:
        vitals_desc.append(f"Heart rate: {heart_rate} bpm")
    if respiratory_rate is not None:
        vitals_desc.append(f"Respiratory rate: {respiratory_rate}/min")
    if oxygen_saturation is not None:
        vitals_desc.append(f"Oxygen saturation: {oxygen_saturation}%")
    if weight_kg is not None:
        vitals_desc.append(f"Weight: {weight_kg} kg")
    if height_cm is not None:
        vitals_desc.append(f"Height: {height_cm} cm")

    if not vitals_desc:
        logger.debug("LLM urgency skip: no vitals to assess")
        return None

    if not patient_age or str(patient_age).strip().upper() in ("N/A", "UNKNOWN", ""):
        logger.warning("Patient age missing (N/A or unknown) — LLM may use adult norms for pediatric patients")

    prompt = f"""Assess triage urgency from these vital signs. Reply with JSON only: {{"urgency_level": "emergency"|"urgent"|"normal", "reasons": ["reason1", "reason2"]}}

Patient: age={patient_age or 'unknown'}, sex={patient_sex or 'unknown'}
Vitals: {"; ".join(vitals_desc)}

JSON:"""

    try:
        logger.debug("LLM urgency: calling OpenAI with vitals=%s", vitals_desc)
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a triage nurse assistant. Classify urgency as emergency (immediate care), urgent (prompt care), or normal (routine). Reply only with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw).replace("```", "").strip()
        data = json.loads(raw)
        level = (data.get("urgency_level") or "normal").lower()
        if level not in ("emergency", "urgent", "normal"):
            level = "normal"
        reasons = data.get("reasons") or []
        if isinstance(reasons, list):
            reasons = [str(r) for r in reasons[:5]]
        else:
            reasons = []
        logger.info("LLM urgency result: level=%s reasons=%s", level, reasons)
        return VitalsUrgencyResult(
            urgency_level=level,
            reasons=reasons,
            score=95 if level == "emergency" else (65 if level == "urgent" else 20),
        )
    except Exception as e:
        logger.warning("LLM urgency failed (fallback to rule-based): %s", type(e).__name__, exc_info=False)
        return None


def default_urgency_stub() -> dict:
    """Return default urgency when symptom-based scoring is not used (vitals-only triage)."""
    return {
        "level": "non_urgent",
        "score": 0,
        "reasons": ["Urgency is assessed from vitals at triage only."],
        "critical_flags": [],
    }


def score_vitals_urgency(
    patient_age: str | None = None,
    patient_sex: str | None = None,
    temperature: float | None = None,
    heart_rate: int | float | None = None,
    respiratory_rate: int | float | None = None,
    oxygen_saturation: float | None = None,
    weight_kg: float | None = None,
    height_cm: float | None = None,
    bp_systolic: float | None = None,
    bp_diastolic: float | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Compute urgency from vitals. Uses rule-based logic; optionally enhances with LLM when configured.
    Returns dict with urgency_level, reasons, score, and method (rule_based | llm).
    """
    # Normalize inputs
    temp = float(temperature) if temperature is not None else None
    hr = int(heart_rate) if heart_rate is not None else None
    rr = int(respiratory_rate) if respiratory_rate is not None else None
    spo2 = float(oxygen_saturation) if oxygen_saturation is not None else None
    sys = float(bp_systolic) if bp_systolic is not None else None
    dia = float(bp_diastolic) if bp_diastolic is not None else None

    age_years = _parse_age_years(patient_age)

    result = _rule_based_urgency(
        temperature=temp,
        bp_systolic=sys,
        bp_diastolic=dia,
        heart_rate=hr,
        respiratory_rate=rr,
        oxygen_saturation=spo2,
        age_years=age_years,
    )

    method = "rule_based"

    if use_llm and (sys or dia or rr):
        llm_result = _llm_urgency(
            temperature=temp,
            bp_systolic=sys,
            bp_diastolic=dia,
            heart_rate=hr,
            respiratory_rate=rr,
            oxygen_saturation=spo2,
            weight_kg=weight_kg,
            height_cm=height_cm,
            patient_age=patient_age,
            patient_sex=patient_sex,
        )
        if llm_result is not None:
            llm_score_map = {"emergency": 95, "urgent": 65, "normal": 20}
            rule_score_map = {"emergency": 90, "urgent": 60, "normal": 25}
            llm_score = llm_score_map.get(llm_result.urgency_level, 20)
            rule_score = rule_score_map.get(result.urgency_level, 25)
            if llm_score >= rule_score or llm_result.urgency_level == "emergency":
                result = llm_result
                method = "llm"
            elif result.urgency_level == "emergency":
                method = "rule_based"

    return {
        "urgency_level": result.urgency_level,
        "reasons": result.reasons,
        "score": result.score,
        "method": method,
    }
