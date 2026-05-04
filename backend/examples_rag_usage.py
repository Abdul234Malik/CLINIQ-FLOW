"""
Example: Testing AI-Powered RAG for Medication Dosage
=====================================================

This script demonstrates how to use the new AI-powered RAG system
for intelligent medication dosing and clinical guideline retrieval.
"""

# Example 1: Initialize Guidelines (Run once at startup)
# ======================================================

from backend.app.services.rag.ingest import initialize_guidelines

result = initialize_guidelines()
print("📚 Clinical Guidelines Initialized:")
print(f"  ✓ Documents indexed: {result.get('documents_indexed', 0)}")
print(f"  ✓ Files processed: {result.get('files_processed', 0)}")
print(f"  ✓ Status: {result.get('status')}")
print()


# Example 2: Retrieve Contextual Guidelines for a Drug
# =====================================================

from backend.app.services.rag.retriever import retrieve_contextual_dosage

guidelines = retrieve_contextual_dosage(
    drug_name="Paracetamol",
    patient_age=7,
    patient_weight=22,
    indication="fever",
    top_k=3
)

print("🔍 AI-Powered Guideline Retrieval:")
print(f"  Drug: {guidelines['drug']}")
print(f"  Patient: {guidelines['patient_context']}")
print(f"  AI Enhanced: {guidelines['ai_enhanced']}")
print(f"  Relevant Guidelines Found: {len(guidelines['relevant_guidelines'])}")

for i, gl in enumerate(guidelines['relevant_guidelines'], 1):
    print(f"\n  Guideline {i}:")
    print(f"    Source: {gl['source']}")
    print(f"    Relevance: {gl['relevance_score']:.2%}")
    print(f"    Text: {gl['text'][:150]}...")

print(f"\n  Fall back formulas available:")
print(f"    - Clark's Rule: {guidelines['formulas']['clarks_rule']}")
print(f"    - Young's Rule: {guidelines['formulas']['youngs_rule']}")
print()


# Example 3: Get AI-Powered Dose Recommendation
# ==============================================

from backend.app.services.rag.retriever import get_ai_dose_recommendation

recommendation = get_ai_dose_recommendation(
    drug_name="Amoxicillin",
    adult_dose_mg=500,
    patient_age=6,
    patient_weight=20,
    indication="strep throat"
)

print("💊 AI-Powered Dose Recommendation:")
print(f"  Drug: {recommendation['drug']}")
print(f"  Adult Dose: {recommendation['adult_dose_mg']}mg")
print(f"\n  Recommended Pediatric Dose:")
print(f"    - Amount: {recommendation['recommended_dose']['mg']}mg")
print(f"    - Method: {recommendation['recommended_dose']['calculation_method']}")
print(f"    - Confidence: {recommendation['recommended_dose']['confidence']}")
print(f"\n  Guidelines Consulted: {len(recommendation['guidelines_consulted'])} excerpts")
print(f"  Warnings: {recommendation['warnings']}")
print()


# Example 4: Integrating with Orchestration Pipeline
# ==================================================

from backend.app.services.rag.guardrails import apply_guardrails

# Simulate clinical decision
clinical_summary = (
    "For a 6-year-old (20kg) with strep throat, prescribe Amoxicillin 250mg "
    "three times daily. Administer with food to reduce GI upset."
)

# Apply guardrails (sanitize, add disclaimer)
safe_output = apply_guardrails(clinical_summary)

print("🛡️  Safety Guardrails Applied:")
print(f"  Original: {clinical_summary}")
print(f"\n  Sanitized: {safe_output['text']}")
print(f"\n  Disclaimer: {safe_output['disclaimer']}")
print()


# Example 5: Dose Safety Check
# =============================

print("✅ Dose Safety Check:")

prescribed_dose = 250  # mg
recommended_dose = recommendation['recommended_dose']['mg']
tolerance = 0.2  # 20% tolerance

is_safe = abs(prescribed_dose - recommended_dose) / recommended_dose < tolerance
status = "✓ SAFE" if is_safe else "⚠ REVIEW RECOMMENDED"

print(f"  Prescribed: {prescribed_dose}mg")
print(f"  Recommended: {recommended_dose}mg")
print(f"  Status: {status}")
print(f"  Variance: {abs(prescribed_dose - recommended_dose) / recommended_dose:.1%}")
print()


# Example 6: Getting Pipeline Status
# ==================================

from backend.app.services.rag.ingest import get_pipeline

pipeline = get_pipeline()
status = pipeline.get_ingestion_status()

print("📊 RAG Pipeline Status:")
print(f"  Vector DB Ready: {status['vector_db_ready']}")
print(f"  Embeddings Available: {status['embeddings_available']}")
print(f"  Fallback Mode: {status['fallback_mode']}")
print(f"  Documents Indexed: {status['registry']}")
print()


# Integration Example: Modified orchestration pipeline
# ====================================================

def enhanced_orchestration_dose_check(
    drug_name: str,
    dose_mg: float,
    patient_age: int,
    patient_weight: float,
    indication: str
) -> dict:
    """
    Enhanced orchestration function that uses AI-powered RAG
    for intelligent dose checking and clinical decision support.
    """
    
    # Step 1: Get AI recommendation based on guidelines
    ai_rec = get_ai_dose_recommendation(
        drug_name=drug_name,
        adult_dose_mg=dose_mg,
        patient_age=patient_age,
        patient_weight=patient_weight,
        indication=indication
    )
    
    # Step 2: Validate prescribed dose against recommendation
    recommended = ai_rec["recommended_dose"]["mg"]
    tolerance = 0.2  # 20% tolerance
    
    if recommended is None:
        variance = float('inf')
        is_safe = False
        safety_level = "UNABLE_TO_ASSESS"
    else:
        variance = abs(dose_mg - recommended) / recommended
        is_safe = variance < tolerance
        safety_level = "SAFE" if is_safe else "REVIEW_RECOMMENDED"
    
    # Step 3: Prepare response with guardrails
    summary = f"Prescribed {dose_mg}mg {drug_name} for {patient_age}yo ({patient_weight}kg) with {indication}. "
    summary += f"AI recommendation: {recommended}mg via {ai_rec['recommended_dose']['calculation_method']}."
    
    safe_summary = apply_guardrails(summary)
    
    return {
        "drug": drug_name,
        "prescribed_mg": dose_mg,
        "recommended_mg": recommended,
        "variance_percent": variance * 100 if variance != float('inf') else None,
        "safety_level": safety_level,
        "confidence": ai_rec["recommended_dose"]["confidence"],
        "guidelines_consulted": len(ai_rec["guidelines_consulted"]),
        "clinical_summary": safe_summary["text"],
        "disclaimer": safe_summary["disclaimer"],
        "ai_enabled": ai_rec["validation"].get("ai_guidelines_consulted", False)
    }


# Test the enhanced orchestration
print("\n🔬 Enhanced Orchestration Test:")
print("=" * 50)

result = enhanced_orchestration_dose_check(
    drug_name="Ibuprofen",
    dose_mg=200,
    patient_age=8,
    patient_weight=25,
    indication="fever"
)

print(f"Drug: {result['drug']}")
print(f"Prescribed: {result['prescribed_mg']}mg")
print(f"Recommended: {result['recommended_mg']}mg")
print(f"Variance: {result['variance_percent']:.1f}%" if result['variance_percent'] is not None else "N/A")
print(f"Safety Status: {result['safety_level']}")
print(f"Confidence: {result['confidence']}")
print(f"Guidelines Consulted: {result['guidelines_consulted']}")
print(f"AI Enabled: {result['ai_enabled']}")
print(f"\nClinical Summary:\n  {result['clinical_summary']}")
print(f"\nDisclaimer:\n  {result['disclaimer']}")
