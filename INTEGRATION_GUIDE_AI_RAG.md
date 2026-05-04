# Integration Guide: Adding AI to Your Medication Dosage Orchestration

## Quick Start

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
# Installs: chromadb, PyPDF2, python-docx
```

### Step 2: Initialize Guidelines on Startup
In `backend/app/main.py`:

```python
from fastapi import FastAPI
from app.services.rag.ingest import initialize_guidelines

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Initialize RAG guideline database on app startup."""
    print("🚀 Initializing clinical guidelines...")
    result = initialize_guidelines()
    print(f"✓ {result['documents_indexed']} clinical documents indexed")
    
    # Optional: log to database
    # storage.log_system_event("rag_initialization", result)
```

### Step 3: Update Orchestration Pipeline
In `backend/app/services/orchestration/pipeline.py`:

```python
# Add these imports at the top
from app.services.rag.retriever import get_ai_dose_recommendation
from app.services.rag.guardrails import apply_guardrails

# Enhance the existing _check_dose_route function
async def _check_dose_route(
    drug_name: str,
    dose_mg: float,
    patient_age: int,
    patient_weight: float,
    indication: str
) -> dict:
    """
    Enhanced dose checking with AI-powered guidelines.
    
    Returns:
        {
            "safe": bool,
            "recommended_mg": float,
            "variance_percent": float,
            "confidence": str,
            "guidelines": int,
            "summary": str,
            "disclaimer": str,
            "warnings": [str],
        }
    """
    
    # Get AI-powered recommendation
    ai_rec = get_ai_dose_recommendation(
        drug_name=drug_name,
        adult_dose_mg=dose_mg,
        patient_age=patient_age,
        patient_weight=patient_weight,
        indication=indication
    )
    
    # Validate against recommendation
    recommended_mg = ai_rec["recommended_dose"]["mg"]
    
    if recommended_mg is None:
        return {
            "safe": False,
            "error": "Cannot calculate dose; insufficient patient data",
            "warnings": ai_rec["warnings"]
        }
    
    # Check variance (allow ±20% tolerance)
    variance = abs(dose_mg - recommended_mg) / recommended_mg
    tolerance = 0.20
    is_safe = variance < tolerance
    
    # Build response
    summary = (
        f"Prescribed {dose_mg}mg {drug_name} for {patient_age}yo ({patient_weight}kg). "
        f"Guideline recommends {recommended_mg:.1f}mg "
        f"via {ai_rec['recommended_dose']['calculation_method']}."
    )
    
    # Apply safety guardrails
    safe_output = apply_guardrails(summary)
    
    return {
        "safe": is_safe,
        "recommended_mg": recommended_mg,
        "prescribed_mg": dose_mg,
        "variance_percent": variance * 100,
        "confidence": ai_rec["recommended_dose"]["confidence"],
        "guidelines_consulted": len(ai_rec["guidelines_consulted"]),
        "summary": safe_output["text"],
        "disclaimer": safe_output["disclaimer"],
        "warnings": ai_rec["warnings"] + (
            ["Variance exceeds 20% tolerance"] if not is_safe else []
        )
    }
```

### Step 4: Add RAG Routes (Optional)
In `backend/app/api/rag_routes.py`:

```python
from fastapi import APIRouter, Query
from app.services.rag.retriever import retrieve_contextual_dosage

router = APIRouter(prefix="/rag", tags=["RAG"])

@router.get("/dosage-guidelines")
async def get_dosage_guidelines(
    drug_name: str,
    age: int = Query(None),
    weight: float = Query(None),
    indication: str = Query(None)
):
    """
    Retrieve AI-powered clinical dosage guidelines.
    
    Query Parameters:
    - drug_name: Medication name (required)
    - age: Patient age in years
    - weight: Patient weight in kg
    - indication: Clinical reason for medication
    
    Returns contextual guidelines with relevance scores.
    """
    result = retrieve_contextual_dosage(
        drug_name=drug_name,
        patient_age=age,
        patient_weight=weight,
        indication=indication,
        top_k=5
    )
    
    # Filter for API response
    return {
        "drug": result["drug"],
        "patient_context": result["patient_context"],
        "guidelines": [
            {
                "source": g["source"],
                "relevance": g["relevance_score"],
                "excerpt": g["text"][:300]
            }
            for g in result["relevant_guidelines"]
        ],
        "ai_enhanced": result["ai_enhanced"]
    }
```

### Step 5: Register RAG Router
In `backend/app/api/router.py`:

```python
from app.api import rag_routes, orchestration_routes, ...

def setup_routes(app: FastAPI):
    """Register all API routers."""
    
    # Add RAG routes
    app.include_router(rag_routes.router)
    
    # ... existing routes
```

## Testing

### Test 1: Initialize Guidelines
```python
from app.services.rag.ingest import initialize_guidelines

result = initialize_guidelines()
assert result["status"] in ["success", "partial"]
assert result["documents_indexed"] > 0
print(f"✓ Indexed {result['documents_indexed']} documents")
```

### Test 2: Retrieve Guidelines
```python
from app.services.rag.retriever import retrieve_contextual_dosage

guidelines = retrieve_contextual_dosage(
    drug_name="Paracetamol",
    patient_age=5,
    patient_weight=18,
    indication="fever"
)

assert guidelines["drug"] == "Paracetamol"
assert len(guidelines["relevant_guidelines"]) > 0
print(f"✓ Retrieved {len(guidelines['relevant_guidelines'])} guidelines")
```

### Test 3: Get Dose Recommendation
```python
from app.services.rag.retriever import get_ai_dose_recommendation

rec = get_ai_dose_recommendation(
    drug_name="Amoxicillin",
    adult_dose_mg=500,
    patient_age=6,
    patient_weight=20
)

assert rec["recommended_dose"]["mg"] is not None
assert rec["recommended_dose"]["confidence"] in ["HIGH", "MEDIUM", "LOW"]
print(f"✓ Recommended: {rec['recommended_dose']['mg']}mg")
```

### Test 4: Full Orchestration
```python
from app.services.orchestration.pipeline import _check_dose_route

result = _check_dose_route(
    drug_name="Ibuprofen",
    dose_mg=200,
    patient_age=8,
    patient_weight=25,
    indication="fever"
)

assert "safe" in result
assert "summary" in result
print(f"✓ Dose check: {result['safe']} (variance: {result['variance_percent']:.1f}%)")
```

## Environment Setup

### .env Configuration
```env
# OpenAI Embeddings
OPENAI_API_KEY=sk-your-key-here

# Optional: Custom vector DB location
RAG_VECTORDB_PATH=./backend/.vectordb

# Optional: Embedding model (default: text-embedding-3-small)
# RAG_EMBEDDING_MODEL=text-embedding-3-small
```

### First Run
On first run, the system will:
1. Scan `backend/app/services/rag/files/`
2. Parse all PDFs, TXT, DOCX files
3. Generate embeddings (~30 seconds)
4. Store in Chroma vector DB (~10-50MB)

Subsequent runs reuse the indexed database.

## Troubleshooting

### Issue: "OpenAI API key not set"
**Solution**: 
```bash
export OPENAI_API_KEY=sk-...
# or add to .env file
```

### Issue: "chromadb not installed"
**Solution**: 
```bash
pip install chromadb>=0.4.0
```

Falls back to in-memory embedding cache automatically.

### Issue: "No documents found to ingest"
**Solution**: Ensure files exist in:
```
backend/app/services/rag/files/
  ├── Clark_Rule_for_Paediatric_Prescription.txt
  ├── Young_Rule_for_Paediatric_Prescription.txt
  ├── PEDIATRIC_MEDICATIONS_DOSE_CALCULATOR.pdf
  └── ...
```

### Issue: "Vector DB search returns empty results"
**Solution**: 
- Check that initialization completed: `initialize_guidelines()`
- Verify files are readable: `ls -la backend/app/services/rag/files/`
- Check `.vectordb/` directory was created

## Performance Tips

1. **First Load**: ~30 seconds (normal, happens once)
2. **Query Latency**: 50-200ms (Chroma + OpenAI)
3. **Memory**: ~100-200MB (vector DB + in-memory cache)

### Optimize for Production
```python
# Use batch embeddings
embeddings = embedder.embed_batch(documents)  # ~2-5x faster

# Increase Chroma batch size
settings = Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory=str(persist_dir),
    anonymized_telemetry=False,
    max_batch_size=1000  # Increase from default 100
)

# Cache query embeddings
query_cache = {}  # Memoize repeated queries
```

## What's Now AI-Powered

✅ **Before**: Pure rule-based formulas (Clark's, Young's)
✅ **After**: AI + Rules (semantic search + formulas)

| Aspect | Before | After |
|--------|--------|-------|
| Dose Calculation | Fixed formulas | Formulas + contextual guidelines |
| Guideline Lookup | Manual search | Semantic AI search |
| Patient Context | Age/weight only | Age/weight/indication/patient profile |
| Confidence Scores | None | HIGH/MEDIUM/LOW |
| Validation | Basic math | Guidelines-based validation |

## Next Steps

1. ✅ Install dependencies: `pip install -r requirements.txt`
2. ✅ Initialize guidelines: Call `initialize_guidelines()` in startup
3. ✅ Update orchestration: Use new dose functions
4. ✅ Add RAG routes: Expose via API
5. ✅ Test integration: Run example scenarios
6. 🔜 Monitor performance: Track embedding generation time
7. 🔜 Fine-tune embeddings: Domain-specific training on clinical data
8. 🔜 Add real-time alerts: Contraindication checking

## Support & Questions

For issues or questions:
1. Check logs: `backend/.vectordb/chroma.log`
2. Review examples: `backend/examples_rag_usage.py`
3. Test components individually
4. Enable debug logging: `logging.getLogger("app.services.rag").setLevel(DEBUG)`
