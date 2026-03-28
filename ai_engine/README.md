# AI Engine

FastAPI-based microservice for AI/ML operations: NLP extraction, ASR transcription, and medical guideline retrieval.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your Supabase and OpenAI credentials

# Run the AI Engine
python main.py
```

The AI Engine will start on `http://localhost:8001`

## Architecture

- **NLP Routes** (`/nlp/*`) — Symptom extraction, SOAP note generation, clinical validation
- **ASR Routes** (`/asr/*`) — Audio transcription with speaker diarization
- **RAG Routes** (`/rag/*`) — Medical guideline retrieval and dose calculations

## API Authentication

All endpoints require the `Authorization: Bearer <AI_ENGINE_TOKEN>` header.

Backend passes token via environment variable `AI_ENGINE_TOKEN`.

## Environment Variables

- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_KEY` — Supabase anonymous key
- `DATABASE_URL_SUPABASE` — Full Postgres connection string
- `AI_ENGINE_TOKEN` — Shared secret for Backend→AI Engine communication
- `OPENAI_API_KEY` — OpenAI API key (for LLM-based services)
- `AI_ENGINE_PORT` — Port to run on (default: 8001)
- `DEBUG` — Enable debug logging (default: False)

## Integration with Backend

The Backend (port 8000) calls the AI Engine via REST API:

```python
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://ai_engine:8001/nlp/extract",
        json=request.dict(),
        headers={"Authorization": f"Bearer {AI_ENGINE_TOKEN}"}
    )
```

## Development

Run with auto-reload:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

## Testing

```bash
pytest tests/
```
