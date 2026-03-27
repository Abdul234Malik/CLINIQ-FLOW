# CLINICAL_RULES.MD
## CliniqFlow - Clinical Structuring Module
## Version: 1.0  
## Last Updated: Phase 3,  


---

## Table of Contents
1. [Safety Rules](#1-safety-rules)
2. [Required Fields Schema](#2-required-fields-schema)
3. [Confidence Level Thresholds](#3-confidence-level-thresholds)
4. [Clinical Flags & Danger Signs](#4-clinical-flags--danger-signs)
5. [Symptom Normalization Dictionary](#5-symptom-normalization-dictionary)
6. [Vital Signs Normal Ranges](#6-vital-signs-normal-ranges)
7. [Extraction Method Priority](#7-extraction-method-priority)
8. [API Contract](#8-api-contract)
9. [Testing Checklist](#9-testing-checklist)

---

## 1. Safety Rules

### S-1: NO DIAGNOSIS STATEMENTS
**Rule:** The system MUST NEVER output diagnosis statements.

**Forbidden Phrases:**
- "Patient has [disease name]"
- "Diagnosed with [condition]"
- "This is [diagnosis]"
- "Likely [disease]" 
- "Probably [condition]"
- "Consistent with [diagnosis]"

**Regex Detection:**
```python
FORBIDDEN_DIAGNOSIS_PHRASES = [
    r'\b(diagnosed with|diagnosis of|has been diagnosed)\b',
    r'\b(patient has|child has)\s+(malaria|pneumonia|typhoid|meningitis)',
    r'\b(this is|likely|probably)\s+\w+itis\b',
    r'\b(consistent with|suggestive of|indicates)\s+\w+',
]
```

**Allowed Alternative:**
- "Patient presents with symptoms consistent with clinical presentation"
- "Clinical findings documented above"
- "Requires clinician assessment"

---

### S-2: NO TREATMENT DECISIONS
**Rule:** The system MUST NEVER prescribe medication or recommend treatment.

**Forbidden Phrases:**
- "Give [drug name]"
- "Administer [medication]"
- "Prescribe [drug]"
- "Treat with [medication]"
- "Start [drug] at [dose]"

**Regex Detection:**
```python
FORBIDDEN_TREATMENT_PHRASES = [
    r'\b(give|administer|prescribe)\s+\w+',
    r'\b(start|begin|commence)\s+\w+\s+(mg|ml|tablets)',
    r'\b(treat with|therapy with)\s+\w+',
    r'\d+\s*(mg|ml|tablets|capsules)',
]
```

**Allowed Alternative:**
- "Clinician to determine appropriate treatment"
- "Refer to Standard Treatment Guidelines"
- "Doctor to prescribe as appropriate"

---

### S-3: MANDATORY DISCLAIMER
**Rule:** All SOAP Assessment and Plan sections MUST include disclaimers.

**Assessment Disclaimer (REQUIRED):**
```
DISCLAIMER: This assessment section is an AI-generated summary of reported 
information only. It does not constitute a clinical diagnosis. All interpretation 
must be performed by a licensed healthcare provider.
```

**Plan Disclaimer (REQUIRED):**
```
PLAN DISCLAIMER: This section contains NO medication dosages, NO treatment 
decisions, and NO diagnostic conclusions. It is a pre-consultation aide only.
```



### S-4: CLINICIAN AUTHORITY
**Rule:** All outputs must emphasize final decision authority rests with the clinician.

**Required Language:**
- "Clinician to review..."
- "Doctor to confirm..."
- "Requires clinical assessment..."
- "Final decisions remain with treating physician..."


## 2. Required Fields Schema

### Minimum Data Requirements

**CRITICAL (System will warn if missing):**
- `session_id` - Unique encounter identifier
- `chief_complaint` - Primary reason for visit
- `symptoms` - At least ONE symptom with raw_text
- `patient_age` - Age of patient (or date of birth)

**HIGHLY RECOMMENDED:**
- `patient_sex` - Male/Female
- `patient_weight` - In kg (essential for dosing)
- `temperature` - Vital sign
- `symptom_duration` - How long symptoms present

**OPTIONAL:**
- `medical_history` - Past conditions
- `allergies` - Drug/food allergies
- `immunization_status` - Vaccination history
- `family_history` - Relevant family conditions

### Data Quality Flags

| Missing Field | Warning Level | Impact |
|--------------|---------------|--------|
| session_id | ERROR | Cannot process |
| chief_complaint | ERROR | Cannot generate SOAP |
| symptoms (0) | ERROR | No clinical data |
| patient_age | WARNING | Cannot assess urgency properly |
| patient_weight | WARNING | Cannot calculate drug doses |
| temperature | INFO | Incomplete vital signs |

---

## 3. Confidence Level Thresholds

### Overall Extraction Confidence

| Level | Score Range | Meaning | Action |
|-------|-------------|---------|--------|
| HIGH | ≥ 0.85 | Excellent extraction quality | Proceed normally |
| MEDIUM | 0.60 - 0.84 | Acceptable quality | Flag for review |
| LOW | 0.30 - 0.59 | Poor quality | Warn user, use with caution |
| CRITICAL | < 0.30 | Unusable data | Trigger fallback extraction |

### Confidence Calculation Factors

**Base Score Components:**
1. **Keyword Match Score** (0-30 points)
   - Each symptom keyword match: +3 points
   - Max 10 symptoms considered
   
2. **Field Completeness** (0-40 points)
   - Chief complaint present: +10 points
   - Age present: +10 points
   - Duration extracted: +10 points
   - Vital signs present: +10 points
   
3. **Extraction Method** (0-30 points)
   - LLM + Rule-based agree: +30 points
   - LLM only: +20 points
   - Rule-based only: +10 points

**Formula:**
```python
overall_confidence = (keyword_score + completeness_score + method_score) / 100
```

### Individual Symptom Confidence

| Confidence | Criteria |
|-----------|----------|
| ≥ 0.90 | Exact keyword match + duration + severity |
| 0.70-0.89 | Keyword match + one attribute |
| 0.50-0.69 | Keyword match only |
| < 0.50 | Fuzzy match or inferred |

---

## 4. Clinical Flags & Danger Signs

### Flag Types

1. **DANGER_SIGN** - Immediate referral required (WHO IMCI)
2. **HIGH_PRIORITY** - Urgent attention needed
3. **MODERATE_PRIORITY** - Standard follow-up
4. **INFORMATIONAL** - Note for clinician

### Critical Danger Signs (WHO/IMCI)

**IMMEDIATE REFERRAL (Urgency Score = 100):**

| Symptom | Keywords | Flag Description |
|---------|----------|------------------|
| Convulsion | convulsion, seizure, fitting, jerking, shaking | 🚨 Convulsion/seizure is a danger sign requiring immediate attention |
| Difficulty Breathing | difficulty breathing, fast breathing, breathless, wheezing, chest indrawing | 🚨 Difficulty breathing is a danger sign requiring immediate attention |
| Altered Consciousness | unconscious, unresponsive, lethargic, drowsy, not alert | 🚨 Altered consciousness requires immediate assessment |
| Unable to Feed | unable to drink, cannot breastfeed, refusing all feeds | 🚨 Unable to feed/drink is a danger sign in children |
| Severe Dehydration | sunken eyes, no tears, no urine, very dry mouth | 🚨 Signs of severe dehydration detected |
| Central Cyanosis | blue lips, blue tongue, bluish skin | 🚨 Central cyanosis requires immediate oxygen therapy |

### High Priority Flags (Urgency Score = 70-90)

| Condition | Detection Logic | Flag Message |
|-----------|----------------|--------------|
| High Fever in Infant | temp ≥39°C AND age <3 months | ⚠️ High fever in young infant requires urgent assessment |
| Prolonged Fever | fever duration >7 days | ⚠️ Fever >7 days requires investigation |
| Persistent Vomiting | vomiting + duration >24 hours | ⚠️ Persistent vomiting may cause dehydration |
| Blood in Stool | keywords: blood in stool, bloody diarrhoea | ⚠️ Blood in stool requires urgent evaluation |
| Severe Pain | keywords: severe pain, crying inconsolably | ⚠️ Severe pain requires immediate assessment |
| Multiple Severe Symptoms | ≥2 symptoms with severity=HIGH | ⚠️ Multiple severe symptoms detected |

### Moderate Flags (Urgency Score = 40-69)

| Condition | Detection Logic | Flag Message |
|-----------|----------------|--------------|
| Abnormal Vital Signs | Any vital outside normal range | ℹ️ Abnormal vital signs noted |
| Fever 3-7 days | fever duration 3-7 days | ℹ️ Ongoing fever - monitor closely |
| Mild Dehydration | decreased urine, dry mouth (not severe) | ℹ️ Signs of mild dehydration |
| Poor Feeding 2+ days | not eating/drinking well >48 hours | ℹ️ Reduced oral intake noted |

### Age-Specific Considerations

**Neonates (0-28 days):**
- ANY fever >38°C → IMMEDIATE
- Difficulty feeding → HIGH PRIORITY
- Reduced movement → HIGH PRIORITY

**Infants (1-12 months):**
- Fast breathing (≥50/min if <2mo, ≥40/min if 2-12mo) → IMMEDIATE
- Bulging fontanelle → HIGH PRIORITY

**Children (1-5 years):**
- Persistent cough >14 days → MODERATE (TB screening)
- Weight loss/failure to thrive → HIGH PRIORITY

---

## 5. Symptom Normalization Dictionary

### Nigerian Local Terms → Medical Terms

| Local/Common Term | Standard Medical Term | Category |
|-------------------|----------------------|----------|
| "hot body" | fever | Temperature |
| "body heat" | fever | Temperature |
| "peppery body" | fever with discomfort | Temperature |
| "catarrh" | runny nose / URTI | Respiratory |
| "running stomach" | diarrhoea | Gastrointestinal |
| "purging" | diarrhoea/vomiting | Gastrointestinal |
| "loose stool" | diarrhoea | Gastrointestinal |
| "watery stool" | diarrhoea | Gastrointestinal |
| "fitting" | seizure/convulsion | Neurological |
| "jerking" | convulsion | Neurological |
| "weak body" | fatigue/lethargy | General |
| "Apollo" | conjunctivitis | Eye |
| "fast breathing" | tachypnea | Respiratory |
| "noisy breathing" | stridor/wheezing | Respiratory |
| "throwing up" | vomiting | Gastrointestinal |

### Symptom Categories

**Respiratory (15 symptoms):**
- cough, runny_nose, difficulty_breathing, wheezing, fast_breathing, chest_pain, sore_throat, nasal_congestion, sneezing, shortness_of_breath, stridor, chest_indrawing, cyanosis, apnea, hoarseness

**Gastrointestinal (12 symptoms):**
- diarrhoea, vomiting, abdominal_pain, nausea, constipation, blood_in_stool, loss_of_appetite, bloating, reflux, difficulty_swallowing, abdominal_distension, jaundice

**Fever/Systemic (8 symptoms):**
- fever, chills, rigors, night_sweats, weight_loss, failure_to_thrive, malaise, lethargy

**Neurological (6 symptoms):**
- convulsion, seizure, altered_consciousness, headache, irritability, drowsiness

**Dermatological (5 symptoms):**
- rash, skin_redness, itching, bruising, pallor

**ENT (4 symptoms):**
- ear_pain, ear_discharge, hearing_loss, nasal_discharge

**Other (5 symptoms):**
- dehydration, edema, joint_pain, bleeding, difficulty_feeding

---

## 6. Vital Signs Normal Ranges (Paediatric)

### Temperature

| Age Group | Normal Range (°C) | Fever If (°C) |
|-----------|-------------------|---------------|
| Neonates (0-28 days) | 36.5-37.5 | ≥38.0 |
| Infants (1-12 months) | 36.5-37.5 | ≥38.0 |
| Toddlers (1-3 years) | 36.5-37.5 | ≥38.0 |
| Children (3-12 years) | 36.5-37.2 | ≥38.0 |

### Heart Rate (beats/min)

| Age Group | Normal Range | Tachycardia If |
|-----------|--------------|----------------|
| Neonates | 120-160 | >160 |
| Infants | 120-160 | >160 |
| Toddlers | 100-140 | >140 |
| Preschool (3-5yr) | 80-120 | >120 |
| School age (6-12yr) | 70-100 | >100 |

### Respiratory Rate (breaths/min)

| Age Group | Normal Range | Fast Breathing If |
|-----------|--------------|-------------------|
| <2 months | 30-50 | ≥60 |
| 2-11 months | 30-50 | ≥50 |
| 1-5 years | 20-40 | ≥40 |
| >5 years | 15-30 | ≥30 |

### Oxygen Saturation (SpO2)

| Measurement | Normal | Abnormal |
|-------------|--------|----------|
| SpO2 | ≥95% | <95% (moderate), <90% (severe) |

### Weight-for-Age (Malnutrition Screening)

| Z-Score | Classification | Action |
|---------|----------------|--------|
| ≥ -1 SD | Normal | Routine care |
| -1 to -2 SD | At risk | Monitor closely |
| -2 to -3 SD | Moderate malnutrition | Nutritional intervention |
| < -3 SD | Severe malnutrition | Urgent referral |

---

## 7. Extraction Method Priority

### Method Ranking

1. **Hybrid (LLM + Rule-based both agree)** - Confidence: 0.90-1.00
2. **LLM Only** - Confidence: 0.70-0.89
3. **Rule-based Only** - Confidence: 0.50-0.69
4. **Fallback (minimal extraction)** - Confidence: 0.30-0.49

### When to Use Each Method

**Use LLM:**
- Complex phrasing
- Contextual relationships
- Ambiguous symptoms
- When API is available

**Use Rule-based:**
- Simple, clear symptoms
- Offline mode required
- API unavailable
- Performance critical

**Trigger Fallback:**
- Overall confidence <0.30
- No symptoms extracted
- Validation errors >2
- Missing all required fields

---

## 8. API Contract

### POST /nlp/process

**Request:**
```json
{
  "transcript": "5-year-old boy with fever for 3 days and difficulty breathing",
  "patient_age": "5 years",
  "patient_sex": "male",
  "session_id": "optional-custom-id"
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "structured_data": {
    "chief_complaint": "fever and difficulty breathing",
    "symptoms": [
      {
        "name": "fever",
        "raw_text": "fever for 3 days",
        "duration": "3 days",
        "severity": "high",
        "confidence": 0.92
      },
      {
        "name": "difficulty_breathing",
        "raw_text": "difficulty breathing",
        "severity": "critical",
        "confidence": 0.95
      }
    ],
    "demographics": {
      "age": "5 years",
      "sex": "male"
    },
    "clinical_flags": [
      {
        "flag_type": "danger_sign",
        "description": "Difficulty breathing is a danger sign",
        "severity": "critical",
        "triggered_by": "difficulty_breathing"
      }
    ],
    "overall_confidence": 0.87
  },
  "urgency": {
    "level": "immediate",
    "score": 95,
    "reasons": ["Difficulty breathing is a danger sign"],
    "critical_flags": ["difficulty_breathing"]
  },
  "soap_note": {
    "subjective": "Chief Complaint: fever and difficulty breathing\n...",
    "objective": "Vital Signs: Not documented\n...",
    "assessment": "Patient presents with fever, difficulty breathing.\nDISCLAIMER: ...",
    "plan": "1. Clinician to review...\nPLAN DISCLAIMER: ..."
  },
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": ["Weight not documented"],
    "confidence_level": "high"
  },
  "processing_time_ms": 287.4
}
```

---

## 9. Testing Checklist 

### Core Functionality Tests

- [ ] Extract symptoms from transcript with Nigerian terminology
- [ ] Generate complete SOAP note (all 4 sections)
- [ ] Detect danger signs (convulsion, difficulty breathing)
- [ ] Calculate urgency level (immediate/urgent/standard/routine)
- [ ] Validate outputs (no diagnosis, no treatment language)
- [ ] Return proper confidence scores
- [ ] Handle missing fields gracefully
- [ ] Work with rule-based only (API unavailable)
- [ ] Process in <500ms
- [ ] Return proper HTTP status codes

### Edge Cases

- [ ] Very short transcript (<10 words)
- [ ] No symptoms mentioned ("routine checkup")
- [ ] Multiple danger signs
- [ ] Conflicting information
- [ ] Missing age/demographics
- [ ] Invalid input format

### Safety Checks

- [ ] No diagnosis language in any output
- [ ] No treatment recommendations in any output
- [ ] Disclaimers present in Assessment and Plan
- [ ] Forbidden phrases blocked by validator
- [ ] High-risk symptoms flagged correctly

---
 
**Last Updated:** Phase 2, Day 10  
**Next Review:** Phase 3, Day 20
