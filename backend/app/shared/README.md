# Shared Models

This directory contains shared Pydantic models and schemas used across both the **Backend** and **AI Engine** services.

## Purpose

Single source of truth for data contracts between services. Both services import models from this shared package to ensure:
- Consistent data validation
- No schema drift
- Type safety across service boundaries

## Modules

- **clinical_schema.py** — Clinical data models (Symptom, VitalSign, StructuredClinicalData, SOAPNote, ValidationResult, etc.)
- **dose.py** — Medication dose checking requests/responses
- **intake.py** — Patient intake request schema
- **triage.py** — Triage result schema
- **patient.py** — Patient registration and update schemas

## Usage

### In Backend Service:
```python
from shared import StructuredClinicalData, IntakeRequest, DoseCheckRequest
```

### In AI Engine Service:
```python
from shared import SOAPNote, ValidationResult, NLPRequest
```

## Versioning

When modifying shared models:
1. Add backward-compatible fields (new fields with defaults)
2. Do NOT remove fields (breaks existing deployments)
3. Update both frontend and backend API versions together
4. Document breaking changes in commit messages

## Adding New Schemas

1. Create a new file in this directory: `module_name.py`
2. Define Pydantic models
3. Add exports to `__init__.py`
4. Update both services' imports
