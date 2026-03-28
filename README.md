# CliniqFlow

AI-assisted paediatric healthcare platform for Nigeria. Supports patient registration, triage, doctor consultations (SOAP notes, prescriptions), and examination records.

---

## Architecture: 3 Independent Production Services

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (React, port 3000)                                 │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP/REST + Supabase JWT
                   ▼
┌──────────────────────────────────────────────────────────────┐
│ Backend (FastAPI, port 8000) - Business Logic               │
│ • Patient management                                         │
│ • Visit workflows                                            │
│ • Triage data entry                                          │
│ • Shared Models (backend/app/shared/)                        │
│ • Calls AI Engine for NLP/ASR/RAG                            │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP + Shared Secret Token
                   ▼
┌──────────────────────────────────────────────────────────────┐
│ AI Engine (FastAPI, port 8001) - ML Services                │
│ • NLP (symptom extraction, SOAP formatting)                  │
│ • ASR (audio transcription)                                  │
│ • RAG (medical guidelines, dose calculations)                │
│ • Shared Models (ai_engine/app/shared/ - copy of Backend)    │
│ • Direct Supabase access (shared with Backend)               │
└──────────────────────────────────────────────────────────────┘
         │ SQL
         ▼
    Supabase (PostgreSQL)
```

**Only 3 Folders:**
- `frontend/` — React app
- `backend/` — Business logic + shared model definitions
- `ai_engine/` — AI services (uses own copy of shared models from backend)

**Key Design Principle (Production Standard):**
✅ Each microservice is **self-contained** — includes its own copy of shared models  
✅ Models kept **identical** via CI/CD synchronization or generation tools  
✅ **Truly independent** — can be deployed/scaled separately  

---

## Tech Stack

| Layer        | Stack                    |
|--------------|--------------------------|
| Frontend     | React, Vite              |
| Backend      | FastAPI, Supabase        |
| AI Engine    | FastAPI, NLP/ASR/RAG ML  |
| Auth         | Supabase Auth (JWT)      |
| DB           | Supabase (PostgreSQL)    |
| Deployment   | Docker (development)     |

---

## Quick Start

**Prerequisites:** Python 3.10+, Node.js 18+, Supabase project

### Option 1: Docker Compose (Recommended)

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your Supabase credentials and OpenAI API key

# Start all 3 services
docker-compose up --build
```

Services available at:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000` (API docs: `/docs`)
- AI Engine: `http://localhost:8001` (health: `/health`)

### Option 2: Manual Setup

**Terminal 1: AI Engine (port 8001)**
```bash
cd ai_engine
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env    # Edit with Supabase & OpenAI keys
uvicorn main:app --reload --port 8001
```

**Terminal 2: Backend (port 8000)**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # Edit with Supabase keys and AI_ENGINE_URL
uvicorn app.main:app --reload --port 8000
```

**Terminal 3: Frontend (port 3000)**
```bash
cd frontend
npm install
npm run dev
```

---

## Folder Structure

```
CLINIQ-FLOW/
├── frontend/                   (React - unchanged)
│   ├── src/
│   ├── package.json
│   └── ...
│
├── backend/                    (Business Logic + Shared Models)
│   ├── app/
│   │   ├── api/               (patient, visit, triage, clinical routes)
│   │   ├── services/          (business logic: patient, visit, triage, transcript)
│   │   ├── shared/            ⭐ Shared model definitions (used by both services)
│   │   ├── core/
│   │   ├── utils/
│   │   └── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── ai_engine/                  (AI/ML Services)
│   ├── app/
│   │   ├── api/               (NLP, ASR, RAG routes)
│   │   ├── services/          (NLP, ASR, RAG service implementations)
│   │   ├── shared/            ⭐ Copy of Backend's shared models (identical)
│   │   ├── core/
│   │   ├── utils/
│   │   └── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── docker-compose.yml          (Orchestrate all 3 services)
├── .env.example                (Root-level environment variables)
├── README.md                   (This file)
├── QUICK_REFERENCE.md          (Quick lookup guide)
└── REORGANIZATION.md           (Complete migration guide)
```

---

## How Shared Models Work

**Shared models are defined in:**  
`backend/app/shared/` — The source of truth

**Used by:**
- Backend: `from app.shared import IntakeRequest, DoseCheckResponse`
- AI Engine: `from app.shared import SOAPNote, ValidationResult`

**Important:** Each service has its own copy. They are kept identical via:
- Manual synchronization in development
- Automated sync via CI/CD pipeline in production
- Shared schema registry (optional, for advanced setups)

---

## Communication

### Frontend → Backend
- **Protocol:** HTTP/REST
- **Auth:** Supabase JWT token (header: `Authorization: Bearer {jwt}`)
- **Endpoint:** `http://localhost:8000/api/*` or specific health endpoints

### Backend → AI Engine
- **Protocol:** HTTP/REST
- **Auth:** Shared secret token (header: `Authorization: Bearer {AI_ENGINE_TOKEN}`)
- **Example:** `POST http://localhost:8001/nlp/extract-symptoms`
- **Error Handling:** If AI Engine down → Backend returns `503 Service Unavailable`

### Both ↔ Supabase
- **Database:** PostgreSQL via Supabase
- **Auth:** Service key (server-side operations)
- **Direct Access:** Both services connect directly; Backend doesn't proxy DB calls

---

## Environment Variables

### Root Level (`.env.example`)
```
# Frontend
VITE_API_URL=http://localhost:8000

# Backend & AI Engine (shared)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-anon-key
DATABASE_URL_SUPABASE=postgresql+psycopg://...

# Backend specific
AI_ENGINE_URL=http://localhost:8001
AI_ENGINE_TOKEN=dev-secret-key-change-in-production

# AI Engine specific
OPENAI_API_KEY=sk-...
```

---

## Production Checklist

- [ ] Change `AI_ENGINE_TOKEN` to strong random value
- [ ] Set `DEBUG=False` in all `.env` files
- [ ] Configure production Supabase credentials
- [ ] Set up monitoring & alerting for each service
- [ ] Configure auto-restart policies
- [ ] Test failover (AI Engine unavailable scenario)
- [ ] Load test Backend ↔ AI Engine communication
- [ ] Synchronize shared models via CI/CD (not manual)
- [ ] Set up centralized logging
- [ ] Document deployment procedure for ops team

---

## Documentation

- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** — Quick lookup for common tasks
- **[REORGANIZATION.md](REORGANIZATION.md)** — Complete architecture migration guide
- **[backend/README.md](backend/README.md)** — Backend setup & API details
- **[ai_engine/README.md](ai_engine/README.md)** — AI Engine setup & services

---

## Support

For issues or questions, refer to the documentation files above or check service health:

```bash
curl http://localhost:8000/                    # Backend status
curl http://localhost:8001/health              # AI Engine health
curl http://localhost:3000                     # Frontend (if running)
```

---

## Project Structure

```
MAIN/
├── backend/          # FastAPI API
│   ├── app/
│   ├── tests/
│   └── docs/
├── frontend/        # React app
└── README.md
```

---

## License

Private / Proprietary
