# CliniqFlow Backend – Setup for Team

Follow these steps to run the backend without breaking the codebase.

---

## 1. Prerequisites

- **Python 3.10+**
- **Supabase project** (for auth + database)
- **Node.js 18+** (for frontend)

---

## 2. Clone & Install

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

---

## 3. Environment Variables
Copy the example and add your values:

```bash
cp .env.example .env
```

Required in `.env`:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `CLINIQ_AUTH_MODE` | `supabase` |

Optional:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | For NLP/SOAP features |
| `HF_TOKEN` | For ASR recording (Whisper + pyannote) |
| `ASR_ENGINE` | `whisper` to enable recording |

---

## 4. Run the Backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

---

## 5. Run the Frontend

```bash
cd ../frontend
npm install
npm run dev
```

- App: `http://localhost:5173`

---

## 6. What You Should NOT Do

- Do **not** change `requirements.txt` without coordinating
- Do **not** commit `.env` (it contains secrets)
- Do **not** remove version pins (e.g. `fastapi==0.111.0`) – they avoid breakage
- Do **not** install packages globally – always use the project venv

---

