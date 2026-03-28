# CLINIQ-FLOW Architecture Reorganization Summary

## Overview
CLINIQ-FLOW has been reorganized from a **monolithic backend** into **3 independent services** following industry-standard microservices architecture:

1. **Frontend** (port 3000) — React UI
2. **Backend** (port 8000) — Business Logic (patient, visit, triage, transcript management)
3. **AI Engine** (port 8001) — AI/ML Services (NLP, ASR, RAG)

---

## What Changed

### Files Moved (from backend → ai_engine)

#### API Routes
```
backend/app/api/nlp_routes.py          → ai_engine/app/api/nlp_routes.py
backend/app/api/asr_routes.py          → ai_engine/app/api/asr_routes.py
backend/app/api/rag_routes.py          → ai_engine/app/api/rag_routes.py
```

#### Services
```
backend/app/services/nlp/              → ai_engine/app/services/nlp/
backend/app/services/asr/              → ai_engine/app/services/asr/
backend/app/services/rag/              → ai_engine/app/services/rag/
backend/app/services/orchestration/    → ai_engine/app/services/orchestration/
```

### Files Moved (from backend → shared)

**Shared Models (Single Source of Truth)**
```
backend/app/models/clinical_schema.py  → shared/clinical_schema.py
backend/app/schemas/dose.py            → shared/dose.py
backend/app/schemas/intake.py          → shared/intake.py
backend/app/schemas/triage.py          → shared/triage.py
backend/app/schemas/patient.py         → shared/patient.py
```

---

## New Directory Structure

```
CLINIQ-FLOW/
├── frontend/                          (Unchanged - React app)
│   ├── src/
│   ├── package.json
│   └── ...
│
├── backend/                           (Refactored - business logic only)
│   ├── app/
│   │   ├── api/
│   │   │   ├── admin_routes.py        ✓ KEPT
│   │   │   ├── clinical_routes.py     ✓ KEPT
│   │   │   ├── doctor_routes.py       ✓ KEPT
│   │   │   ├── nurse_routes.py        ✓ KEPT
│   │   │   ├── record_officer_routes.py ✓ KEPT
│   │   │   ├── orchestration_routes.py ✓ UPDATED (now calls AI Engine)
│   │   │   ├── router.py              ✓ KEPT
│   │   │   └── endpoints/
│   │   ├── services/
│   │   │   ├── patient_service.py     ✓ KEPT
│   │   │   ├── visit_service.py       ✓ KEPT
│   │   │   ├── triage_service.py      ✓ KEPT
│   │   │   ├── transcript_service.py  ✓ KEPT
│   │   │   └── sync/                  ✓ KEPT
│   │   ├── core/
│   │   │   ├── auth.py                ✓ KEPT
│   │   │   └── database.py            ✓ KEPT
│   │   ├── utils/
│   │   │   ├── config.py              ✓ UPDATED (added AI_ENGINE_URL, token)
│   │   │   ├── auth.py                ✓ KEPT
│   │   │   ├── errors.py              ✓ KEPT
│   │   │   ├── storage.py             ✓ KEPT
│   │   │   └── logging.py             ✓ KEPT
│   ├── main.py                        ✓ UPDATED (removed AI imports)
│   ├── requirements.txt               ✓ UPDATED (removed torch, transformers, openai)
│   ├── .env.example                   ✓ NEW
│   └── README.md                      ✓ NEW
│
├── ai_engine/                         (NEW - AI/ML services)
│   ├── app/
│   │   ├── api/
│   │   │   ├── nlp_routes.py          ✓ MOVED
│   │   │   ├── asr_routes.py          ✓ MOVED
│   │   │   ├── rag_routes.py          ✓ MOVED
│   │   │   ├── health.py              ✓ NEW
│   │   │   └── router.py              ✓ NEW
│   │   ├── services/
│   │   │   ├── nlp/                   ✓ MOVED
│   │   │   ├── asr/                   ✓ MOVED
│   │   │   ├── rag/                   ✓ MOVED
│   │   │   └── orchestration/         ✓ MOVED
│   │   ├── core/
│   │   │   ├── auth.py                ✓ NEW (validates AI_ENGINE_TOKEN)
│   │   │   └── database.py            ✓ NEW (Supabase connection)
│   │   └── utils/
│   │       └── config.py              ✓ NEW
│   ├── main.py                        ✓ NEW
│   ├── requirements.txt               ✓ NEW (torch, transformers, openai, etc.)
│   ├── .env.example                   ✓ NEW
│   └── README.md                      ✓ NEW
│
├── shared/                            (NEW - Shared Models)
│   ├── __init__.py                    ✓ NEW (exports all models)
│   ├── clinical_schema.py             ✓ MOVED
│   ├── dose.py                        ✓ MOVED
│   ├── intake.py                      ✓ MOVED
│   ├── triage.py                      ✓ MOVED
│   ├── patient.py                     ✓ MOVED
│   └── README.md                      ✓ NEW
│
├── docker-compose.yml                 ✓ NEW (orchestrates all 3 services)
├── .env.example                       ✓ NEW (root-level env variables)
├── README.md                          ✓ UPDATED (3-service architecture)
└── ...
```

---

## Code Changes (Minimal, Only Where Necessary)

### Backend Changes

#### 1. `backend/app/main.py` — Remove AI imports
**Before:** Imported nlp_routes, asr_routes from local services  
**After:** Removed AI route imports; keep orchestration_routes (now calls AI Engine)

```python
# REMOVED:
# from app.api.nlp_routes import router as nlp_router
# from app.api.asr_routes import translate_router, conversation_router, lifespan

# KEPT (but updated):
from app.api.orchestration_routes import router as orchestration_routes_router
```

**Reason:** AI services are now external (port 8001)

#### 2. `backend/app/utils/config.py` — Add AI Engine configuration
**Before:** Minimal placeholder  
**After:** Added AI_ENGINE_URL and AI_ENGINE_TOKEN

```python
# NEW:
AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")
AI_ENGINE_TOKEN = os.getenv("AI_ENGINE_TOKEN", "dev-secret-key")
```

**Reason:** Backend needs to know how to reach AI Engine

#### 3. `backend/app/api/orchestration_routes.py` — Call AI Engine via REST
**Before:** Imported and called local services directly
**After:** Makes HTTP requests to AI Engine

```python
# OLD (called local service):
# response = process_intake(payload.model_dump())

# NEW (calls AI Engine via HTTP):
async with httpx.AsyncClient() as client:
    ai_response = await client.post(
        f"{AI_ENGINE_URL}/nlp/process_intake",
        json=payload.model_dump(),
        headers={"Authorization": f"Bearer {AI_ENGINE_TOKEN}"},
        timeout=30.0,
    )
```

**Reason:** AI services live in separate process/container

#### 4. `backend/requirements.txt` — Remove AI dependencies
**Before:** Included torch, transformers, openai, whisper, pyannote  
**After:** Removed (only backend needs fastapi, sqlalchemy, supabase, httpx)

```
# REMOVED:
# torch>=2.2.0
# transformers>=4.41.0
# openai>=1.0.0
# pyannote.audio>=3.1.1
# ...

# ADDED:
# httpx==0.27.0  (for calling AI Engine)
```

**Reason:** Backend no longer needs ML libraries; kept in AI Engine

### Backend Model Imports Updated
All files importing from schemas now import from shared:

```python
# OLD:
# from app.schemas.dose import DoseCheckRequest, DoseCheckResponse

# NEW:
from shared import DoseCheckRequest, DoseCheckResponse
```

**Files changed:**
- `backend/app/api/orchestration_routes.py`

---

## New Services

### AI Engine (`ai_engine/`)

**New Files:**
- `main.py` — FastAPI app entry point
- `app/api/health.py` — Health check endpoints
- `app/api/router.py` — Routes aggregator
- `app/core/auth.py` — Validates AI_ENGINE_TOKEN header
- `app/core/database.py` — Supabase connection
- `app/utils/config.py` — Configuration loading
- `requirements.txt` — AI-specific dependencies
- `.env.example` — Environment template
- `README.md` — AI Engine documentation

**Moved Services:**
- All NLP, ASR, RAG services + orchestration pipeline

---

## Shared Models (`shared/`)

**Purpose:** Single source of truth for data contracts

**New Files:**
- `__init__.py` — Exports all models
- `clinical_schema.py` — Core clinical data models
- `dose.py` — Dose check schemas
- `intake.py` — Patient intake schema
- `triage.py` — Triage result schema
- `patient.py` — Patient registration schemas
- `README.md` — Usage documentation

**Import in Both Services:**
```python
# In Backend:
from shared import IntakeRequest, DoseCheckRequest

# In AI Engine:
from shared import SOAPNote, ValidationResult
```

---

## Configuration & Secrets

### Root `.env.example`
```
# Frontend
VITE_API_URL=http://localhost:8000

# Backend
SUPABASE_URL=...
SUPABASE_KEY=...
DATABASE_URL_SUPABASE=...
AI_ENGINE_URL=http://localhost:8001
AI_ENGINE_TOKEN=dev-secret-key

# AI Engine
OPENAI_API_KEY=sk-...
```

### Backend → AI Engine Communication
- **Protocol:** HTTP/REST
- **Authentication:** Bearer token (shared secret)
- **Header:** `Authorization: Bearer {AI_ENGINE_TOKEN}`
- **Network:** Internal (localhost:8001 or docker container name `ai_engine`)

---

## How to Verify It Works

### 1. Check File Structure
```bash
# Verify new directories exist
ls -la ai_engine/             # Should exist with /app, /main.py
ls -la shared/                # Should exist with model files
```

### 2. Check Backend Imports
```bash
# Backend should NOT import AI services
grep -r "from app.api.nlp_routes" backend/  # Should return nothing
grep -r "from app.api.asr_routes" backend/  # Should return nothing
grep -r "from app.services.nlp" backend/   # Should return nothing
```

### 3. Verify Shared Models
```bash
# Both services should import from /shared/
grep -r "from shared import" backend/      # Should find imports
grep -r "from shared import" ai_engine/    # Should find imports
```

### 4. Test Locally (Manual)

**Terminal 1 - AI Engine:**
```bash
cd ai_engine
export SUPABASE_URL=<your-url>
export SUPABASE_KEY=<your-key>
export OPENAI_API_KEY=<your-key>
export AI_ENGINE_TOKEN=dev-secret-key
uvicorn main:app --reload --port 8001
# Should see: "Application startup complete" on port 8001
```

**Terminal 2 - Backend:**
```bash
cd backend
export SUPABASE_URL=<your-url>
export SUPABASE_KEY=<your-key>
export DATABASE_URL_SUPABASE=<your-url>
export AI_ENGINE_URL=http://localhost:8001
export AI_ENGINE_TOKEN=dev-secret-key
uvicorn app.main:app --reload --port 8000
# Should see: "Application startup complete" on port 8000
```

**Terminal 3 - Test API Call:**
```bash
# Test AI Engine health
curl http://localhost:8001/health
# Response: {"status": "ok", "service": "ai_engine"}

# Test Backend health
curl http://localhost:8000/
# Response: {"message": "CliniqFlow API is running", ...}

# Test Backend → AI Engine call (if data available)
curl -X POST http://localhost:8000/ai/summary \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <supabase-token>" \
  -d '{
    "visit_id": "test-123",
    "transcript": "Patient complains of fever",
    "patient_age": "5 years"
  }'
# Should call AI Engine internally and return SOAP note
```

### 5. Test with Docker Compose
```bash
# Copy env file
cp .env.example .env
# Edit .env with your credentials

# Start all services
docker-compose up --build

# Should see 3 services starting:
# cliniq-frontend (port 3000)
# cliniq-backend (port 8000, waits for ai_engine)
# cliniq-ai-engine (port 8001)

# Test from host machine:
curl http://localhost:8001/health
curl http://localhost:8000/
```

---

## Production Checklist

- [ ] Update `AI_ENGINE_TOKEN` to strong random value (not "dev-secret-key")
- [ ] Update Supabase credentials in `.env`
- [ ] Configure `OPENAI_API_KEY` for LLM services
- [ ] Set `DEBUG=False` in all `.env` files
- [ ] Configure proper logging (`LOG_LEVEL=WARNING`)
- [ ] Set up container orchestration (K8s, Docker Compose, or serverless)
- [ ] Configure health checks and auto-restart
- [ ] Set up monitoring/alerting for each service
- [ ] Test failover when AI Engine is unavailable
- [ ] Load test Backend ↔ AI Engine communication
- [ ] Document deployment procedure for ops team

---

## FAQs

**Q: Why move AI services to separate service?**  
A: Modular design, independent scaling, easier maintenance, aligns with industry best practices (microservices).

**Q: Can Frontend call AI Engine directly?**  
A: No. Frontend always goes through Backend. Backend handles orchestration, logging, and audit trails.

**Q: What if AI Engine goes down?**  
A: Backend returns `503 Service Unavailable` to Frontend. Frontend can retry or show "AI service temporarily offline".

**Q: How does Backend authenticate to AI Engine?**  
A: Shared secret token (environment variable `AI_ENGINE_TOKEN`). Both services must have matching token.

**Q: Are models shared or duplicated?**  
A: Shared from `/shared/` folder. Single source of truth prevents schema drift.

**Q: Can I deploy AI Engine separately from Backend?**  
A: Yes! That's the design. Update `AI_ENGINE_URL` to point to different host/port.

---

## Comments for Layman Understanding

### Key Concept: Separation of Concerns
- **Frontend** — What users see (React UI)
- **Backend** — Business operations (patient data, visit workflow)
- **AI Engine** — Smart thinking (understanding symptoms, transcribing audio)

Like a hospital: reception desk (Frontend), administrative office (Backend), laboratory (AI Engine).

### Why Shared Models?
Imagine a form that Frontend fills and sends to Backend, which forwards to AI Engine. If everyone has their own version of the form, it causes confusion. **Shared models** = everyone uses the same form template.

### Why Shared Secret Token?
Backend and AI Engine are "friends" on the same internal network. They need a password to verify they're really talking to each other (not a hacker). This is the `AI_ENGINE_TOKEN`.

### Communication Flow
```
User (Frontend) sends request
         ↓
    Backend receives
         ↓
    Backend asks "Do I need AI?"
         ↓
    If yes: Backend sends request to AI Engine (with password token)
    If no: Backend handles directly
         ↓
    AI Engine responds
    or Backend responds
         ↓
    Frontend gets result
```

---

## References

- [Backend README](backend/README.md) — Backend-specific setup
- [AI Engine README](ai_engine/README.md) — AI Engine setup
- [Shared Models README](shared/README.md) — Model documentation
- [Root README](README.md) — Architecture overview
