# Quick Reference: 3-Folder Architecture

## Only 3 Folders (Production Architecture)

```
CLINIQ-FLOW/
├── frontend/        (React, port 3000)      — UI only
├── backend/         (FastAPI, port 8000)    — business logic + shared models source
└── ai_engine/       (FastAPI, port 8001)    — AI services (self-contained with model copy)

Also at root:
├── docker-compose.yml
├── .env.example
├── README.md
└── REORGANIZATION.md
```

**Key Detail:** Shared models live inside each service, not in a separate folder:
- `backend/app/shared/` ← source of truth (all model definitions)
- `ai_engine/app/shared/` ← identical copy (synced via CI/CD)

---

## Communication Flow

```
Frontend (3000)
    ↓ HTTP (Supabase JWT)
Backend (8000)
    ├─ Business logic: patient, visit, triage, transcript
    └─ When AI needed → AI Engine (8001)
         ↓ HTTP (Bearer token)
    AI Engine (8001)
         ├ NLP: symptom extraction, SOAP formatting
         ├ ASR: audio transcription
         └ RAG: medical guidelines
```

---

## What Moved Where

### TO AI Engine (3 services + shared models copy)
- ✅ `nlp_routes.py` + `services/nlp/` → `ai_engine/app/api/nlp_routes.py`
- ✅ `asr_routes.py` + `services/asr/` → `ai_engine/app/api/asr_routes.py`
- ✅ `rag_routes.py` + `services/rag/` → `ai_engine/app/api/rag_routes.py`
- ✅ Shared models copy → `ai_engine/app/shared/` (identical to Backend's)

### Backend Now Has (source of truth)
- ✅ **Only business logic:** patient, visit, triage, transcript services
- ✅ **Shared models source:** `backend/app/shared/` (clinical_schema, dose, intake, triage, patient)
- ✅ **Removed:** NLP/ASR/RAG services (moved to AI Engine)
- ✅ **Removed:** torch, transformers, openai, pyannote, whisper (moved to AI Engine)
- ✅ **Updated:** `orchestration_routes.py` calls AI Engine via HTTP instead of local imports

### Shared Models (inside each service)
Location: `backend/app/shared/` (source) + `ai_engine/app/shared/` (copy)
- ✅ `clinical_schema.py` → Symptom, VitalSign, SOAPNote, etc.
- ✅ `dose.py` → DoseCheckRequest/Response
- ✅ `intake.py` → IntakeRequest
- ✅ `triage.py` → TriageResult
- ✅ `patient.py` → BioData, CreatePatient, PatientResponse

---

## Quick Start

### Docker Compose (Recommended)
```bash
cp .env.example .env
# Edit .env with your credentials
docker-compose up --build
```
Services available at:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- AI Engine: `http://localhost:8001`

### Manual Setup
```bash
# Terminal 1: AI Engine (port 8001)
cd ai_engine
pip install -r requirements.txt
uvicorn main:app --port 8001

# Terminal 2: Backend (port 8000)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# Terminal 3: Frontend (port 3000)
cd frontend
npm install && npm run dev
```

---

## Key Environment Variables

| Variable | Purpose | Location |
|----------|---------|----------|
| `SUPABASE_URL` | Database URL | Root .env |
| `SUPABASE_KEY` | Auth key | Root .env |
| `AI_ENGINE_URL` | AI Engine base URL | Backend .env |
| `AI_ENGINE_TOKEN` | Shared secret | Both .env |
| `OPENAI_API_KEY` | LLM API | AI Engine .env |

---

## File Changes Summary

### No Changes to Frontend
Frontend API routes unchanged. All calls go through Backend.

### Backend Changes
| File | Change | Reason |
|------|--------|--------|
| `app/main.py` | Removed AI imports | Services moved to AI Engine |
| `app/api/orchestration_routes.py` | Call AI Engine via HTTP | NLP/ASR now external |
| `app/utils/config.py` | Added AI config vars | Backend needs to reach AI Engine |
| `requirements.txt` | Removed torch, transformers, openai | Moved to AI Engine |

### AI Engine (New)
- Complete FastAPI service with NLP, ASR, RAG
- Shared secret token authentication
- Direct Supabase access (same credentials as Backend)

### Shared (New)
- All data models used by both Backend and AI Engine
- Single source of truth — prevents schema drift

---

## Authentication

### Frontend → Backend
- **Method:** Supabase JWT token
- **Header:** `Authorization: Bearer <jwt_token>`

### Backend → AI Engine
- **Method:** Shared secret token (internal)
- **Header:** `Authorization: Bearer <AI_ENGINE_TOKEN>`
- **Env var:** Must match in both `.env` files

---

## Testing Endpoints

```bash
# Health checks
curl http://localhost:8000/                    # Backend running
curl http://localhost:8001/health              # AI Engine running

# Backend orchestration (calls AI Engine internally)
curl -X POST http://localhost:8000/ai/summary \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"visit_id": "test", "transcript": "fever", "patient_age": "5 years"}'
```

---

## Documentation Files

| File | Purpose |
|------|---------|
| [README.md](README.md) | Architecture overview & quick start |
| [REORGANIZATION.md](REORGANIZATION.md) | Complete migration guide |
| [backend/README.md](backend/README.md) | Backend setup & API details |
| [ai_engine/README.md](ai_engine/README.md) | AI Engine setup & services |

---

## Production Checklist

- [ ] Change `AI_ENGINE_TOKEN` to strong random value
- [ ] Set `DEBUG=False` in all `.env` files
- [ ] Configure production Supabase credentials
- [ ] Set up monitoring for both Backend and AI Engine
- [ ] Configure auto-restart policies
- [ ] Test failover (AI Engine down scenario)
- [ ] Load test Backend ↔ AI Engine communication
- [ ] Set up CI/CD for containerized deployment
- [ ] Document deployment procedure

---

## Get Help

- **Architecture questions?** → See [REORGANIZATION.md](REORGANIZATION.md)
- **Backend issues?** → See [backend/README.md](backend/README.md)
- **AI Engine issues?** → See [ai_engine/README.md](ai_engine/README.md)
- **Shared models (in Backend)?** → See `backend/app/shared/` and `ai_engine/app/shared/`
