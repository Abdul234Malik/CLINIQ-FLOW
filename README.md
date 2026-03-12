# CliniqFlow

AI-assisted paediatric healthcare platform for Nigeria. Supports patient registration, triage, doctor consultations (SOAP notes, prescriptions), and examination records.

---

## Tech Stack

| Layer  | Stack            |
|--------|------------------|
| Backend| FastAPI, Supabase|
| Frontend | React, Vite   |
| Auth   | Supabase Auth    |
| DB     | Supabase (PostgreSQL) |

---

## Quick Start

**Prerequisites:** Python 3.10+, Node.js 18+, Supabase project

1. **Backend**
   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   cp .env.example .env   # Edit with your Supabase keys
   uvicorn app.main:app --reload --port 8000
   ```

2. **Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

- API: http://localhost:8000  
- Docs: http://localhost:8000/docs  
- App: http://localhost:5173  

---

## Full Setup

For env variables, team rules, and troubleshooting:

→ **[backend/docs/SETUP.md](backend/docs/SETUP.md)**

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
