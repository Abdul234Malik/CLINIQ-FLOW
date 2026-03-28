# Backend

FastAPI service handling all business logic: patient management, visit workflows, triage, and clinical operations.

The Backend delegates AI/ML operations to the separate **AI Engine** (port 8001) via REST API.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your Supabase credentials and AI_ENGINE_URL

# Run Backend
python main.py
```

The Backend will start on `http://localhost:8000`

## Architecture

**Three-Tier Flow:**
- **Frontend** (React, port 3000) → Calls Backend API  
- **Backend** (FastAPI, port 8000) → Orchestrates workflows, calls AI Engine
- **AI Engine** (FastAPI, port 8001) → Handles NLP, ASR, RAG services

## API Endpoints

### Clinical Workflows
- `POST /nurse/complete-triage` — Capture vitals (no AI involved)
- `GET /doctor/queue` — List patients waiting for doctor
- `POST /doctor/order-medication` — Validate drug dose

### AI Orchestration (Backend → AI Engine)
- `POST /ai/process_intake` — Extract symptoms via NLP
- `POST /ai/summary` — Generate SOAP note
- `POST /ai/dose-check` — Check medication safety

**Note:** AI endpoints (`/ai/*`) are handled by Backend but call AI Engine internally.

## Communication with AI Engine

Backend calls AI Engine with **internal shared secret authentication**:

```python
# orchestration_routes.py example:
headers = {"Authorization": f"Bearer {AI_ENGINE_TOKEN}"}
response = await client.post(
    f"{AI_ENGINE_URL}/nlp/extract",
    json=payload.dict(),
    headers=headers
)
```

**Error Handling:**
- If AI Engine unavailable (port 8001 down) → Backend returns `503 Service Unavailable`
- Frontend should retry or show "AI service temporarily offline"

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `SUPABASE_URL` | Supabase project URL | `https://xxxxx.supabase.co` |
| `SUPABASE_KEY` | Supabase anon key | `eyJhbGc...` |
| `DATABASE_URL_SUPABASE` | Full Postgres connection | `postgresql+psycopg://...` |
| `AI_ENGINE_URL` | AI Engine base URL | `http://localhost:8001` |
| `AI_ENGINE_TOKEN` | Shared secret for Backend→AI Engine | `dev-secret-key` |
| `BACKEND_PORT` | Port to run on | `8000` |
| `DEBUG` | Enable debug logging | `False` |

## What Moved to AI Engine?

These services moved from Backend to AI Engine (port 8001):
- **NLP services** — Symptom extraction, SOAP formatting, clinical validation
- **ASR services** — Audio transcription with speaker diarization
- **RAG services** — Medical guideline retrieval, dose calculations

Backend now imports shared models from `/shared/` and calls AI Engine endpoints.

## Development

Run with auto-reload:
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Testing

```bash
pytest tests/
```

## Docker

Build and run with docker-compose:
```bash
docker-compose up --build
```

All 3 services start automatically:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- AI Engine: `http://localhost:8001`
