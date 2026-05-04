# RAG (Retrieval-Augmented Generation) Service

AI-powered clinical guideline retrieval for intelligent medication dosing and decision support.

## Components

### 1. **ingest.py** — Document Ingestion Pipeline
Parses clinical guidelines and indexes them with AI embeddings for semantic search.

**Key Functions:**
- `initialize_guidelines()` — Ingest all clinical documents on startup
- `retrieve_dosage_guidelines()` — Semantic search for drug-specific guidelines
- `get_pipeline()` — Access the RAG pipeline singleton

**Features:**
- Auto-parses PDF, TXT, DOCX documents from `files/` directory
- Generates embeddings via OpenAI API (or fallback)
- Stores embeddings in Chroma vector DB for fast retrieval
- Graceful degradation if OpenAI/Chroma unavailable

### 2. **retriever.py** — Guideline Retrieval
Hybrid retrieval combining AI-powered semantic search with rule-based formulas.

**Key Functions:**
- `retrieve_contextual_dosage()` — Get relevant guidelines with patient context
- `get_ai_dose_recommendation()` — Full dose calculation with guideline validation
- `get_clarks_rule_text()` — Static Clark's Rule formula
- `get_youngs_rule_text()` — Static Young's Rule formula

### 3. **guardrails.py** — Safety & Compliance
Sanitizes output and enforces disclaimers.

**Key Functions:**
- `apply_guardrails()` — Removes prescriptive language, adds disclaimers

## Usage Examples

### Example 1: Initialize Guidelines (On Startup)
```python
from app.services.rag.ingest import initialize_guidelines

# In your FastAPI startup event:
@app.on_event("startup")
async def startup():
    result = initialize_guidelines()
    print(f"Ingested {result['documents_indexed']} clinical documents")
```

### Example 2: Contextual Dose Lookup
```python
from app.services.rag.retriever import retrieve_contextual_dosage

# For a pediatric patient on amoxicillin for ear infection:
guidelines = retrieve_contextual_dosage(
    drug_name="amoxicillin",
    patient_age=5,
    patient_weight=18.5,
    indication="ear infection",
    top_k=3
)

print(f"Found {len(guidelines['relevant_guidelines'])} matching guidelines")
for gl in guidelines['relevant_guidelines']:
    print(f"  - {gl['source']}: {gl['text'][:100]}...")
```

### Example 3: AI-Powered Dose Recommendation
```python
from app.services.rag.retriever import get_ai_dose_recommendation

# Get intelligent dose recommendation:
recommendation = get_ai_dose_recommendation(
    drug_name="paracetamol",
    adult_dose_mg=500,
    patient_age=8,
    patient_weight=25,
    indication="fever"
)

result = {
    "drug": recommendation["drug"],
    "recommended_mg": recommendation["recommended_dose"]["mg"],
    "method": recommendation["recommended_dose"]["calculation_method"],
    "confidence": recommendation["recommended_dose"]["confidence"],
    "guidelines_consulted": [g["source"] for g in recommendation["guidelines_consulted"]]
}

print(f"Recommend {result['recommended_mg']}mg via {result['method']}")
```

### Example 4: Integrating with Orchestration Pipeline
```python
# In backend/app/services/orchestration/pipeline.py

from app.services.rag.retriever import get_ai_dose_recommendation
from app.services.rag.guardrails import apply_guardrails

def check_dose_safe(
    drug_name: str,
    dose_mg: float,
    patient_age: int,
    patient_weight: float,
    indication: str
) -> dict:
    """Check medication safety using AI-powered guidelines."""
    
    # Get AI recommendation
    ai_recommendation = get_ai_dose_recommendation(
        drug_name=drug_name,
        adult_dose_mg=dose_mg,
        patient_age=patient_age,
        patient_weight=patient_weight,
        indication=indication
    )
    
    # Check if prescribed dose is within recommendation
    recommended_dose = ai_recommendation["recommended_dose"]["mg"]
    is_safe = abs(dose_mg - recommended_dose) < (recommended_dose * 0.2)  # Within 20%
    
    # Apply safety guardrails
    summary = f"Dose of {dose_mg}mg recommended for {drug_name}. Based on {ai_recommendation['recommended_dose']['calculation_method']}."
    safe_summary = apply_guardrails(summary)
    
    return {
        "drug": drug_name,
        "prescribed_mg": dose_mg,
        "recommended_mg": recommended_dose,
        "is_safe": is_safe,
        "confidence": ai_recommendation["recommended_dose"]["confidence"],
        "guidelines_consulted": len(ai_recommendation["guidelines_consulted"]),
        "summary": safe_summary["text"],
        "disclaimer": safe_summary["disclaimer"]
    }
```

### Example 5: Adding to RAG Routes
```python
# In backend/app/api/rag_routes.py

from fastapi import APIRouter, Query
from app.services.rag.retriever import retrieve_contextual_dosage

router = APIRouter(prefix="/rag", tags=["RAG"])

@router.get("/dosage-guidelines/{drug_name}")
async def get_dosage_guidelines(
    drug_name: str,
    age: int = Query(None),
    weight: float = Query(None),
    indication: str = Query(None)
):
    """Retrieve AI-powered dosage guidelines for a drug."""
    result = retrieve_contextual_dosage(
        drug_name=drug_name,
        patient_age=age,
        patient_weight=weight,
        indication=indication
    )
    return result
```

## Architecture

### Data Flow
1. **Ingestion Phase** (startup)
   - Scan `backend/app/services/rag/files/` for PDF/TXT/DOCX
   - Parse documents into chunks
   - Generate embeddings (OpenAI or fallback)
   - Store in Chroma vector DB

2. **Retrieval Phase** (on API call)
   - Create query embedding from drug + patient context
   - Semantic search in vector DB
   - Return top-k relevant guideline excerpts
   - Combine with rule-based dose calculations

3. **Output Phase**
   - Format recommendations with metadata
   - Apply safety guardrails
   - Return to API with confidence scores

### Graceful Degradation
- **No Chroma**: In-memory fallback caching
- **No OpenAI**: Uses fallback embedding or simple text statistics
- **No guidelines**: Falls back to Clark's/Young's formulas only

## Clinical Guidelines Included

The `files/` directory contains:

| File | Purpose |
|------|---------|
| `Clark_Rule_for_Paediatric_Prescription.txt` | Weight-based pediatric dosing |
| `Young_Rule_for_Paediatric_Prescription.txt` | Age-based pediatric dosing |
| `PEDIATRIC_MEDICATIONS_DOSE_CALCULATOR.pdf` | Comprehensive pediatric dosing |
| `NGA_Nigeria_Essential_Medicine_List_For_Children_2020.pdf` | Nigerian formulary |
| `Standard_Treatment_Manual.pdf` | Clinical protocols |
| `drug_dosage_and_iv_rates_calculations.pdf` | Dosage calculations |
| `Guidelines_For_Clinical_Trials_In_Paediatric_Populations_*.pdf` | Trial protocols |
| Various `.png` drug class images | Visual guidelines |

## Environment Variables

```env
# OpenAI API for embeddings
OPENAI_API_KEY=sk-...

# Optional: Custom vector DB path
RAG_VECTORDB_PATH=/path/to/vectordb
```

## Dependencies

| Package | Purpose | Optional |
|---------|---------|----------|
| `chromadb` | Vector database | Yes (fallback to in-memory) |
| `PyPDF2` | PDF parsing | Yes (skip unsupported files) |
| `python-docx` | DOCX parsing | Yes (skip unsupported files) |

## Performance Notes

- **First ingest**: ~10-30 seconds (depends on file size & OpenAI API)
- **Vector DB lookup**: ~50-200ms (in-memory faster)
- **Embedding generation**: ~500ms per query (with OpenAI)

## Future Enhancements

1. Fine-tune embeddings on clinical text corpus
2. Multi-language support (Pidgin, Yoruba for Nigeria)
3. Real-time dose monitoring & alerts
4. Contraindication checking with AI
5. Personalized recommendations by patient profile
