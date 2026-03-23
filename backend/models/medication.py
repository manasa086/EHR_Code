from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class PatientContext(BaseModel):
    age: int
    conditions: List[str] = []
    recent_labs: Optional[Dict[str, Any]] = {}


class MedicationSource(BaseModel):
    system: str
    medication: str
    last_updated: Optional[str] = None
    last_filled: Optional[str] = None
    source_reliability: str  # "high" | "medium" | "low"


class ReconcileRequest(BaseModel):
    # Core reconciliation fields
    patient_context: PatientContext
    sources: List[MedicationSource]
    # Full case metadata — included so the cache key covers every case field
    id: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    demographics: Optional[Dict[str, Any]] = None
    allergies: Optional[List[str]] = None
    vital_signs: Optional[Dict[str, Any]] = None
    last_updated: Optional[str] = None


class ReconcileResponse(BaseModel):
    reconciled_medication: str
    confidence_score: float
    reasoning: str
    recommended_actions: List[str]
    clinical_safety_check: str  # "PASSED" | "NEEDS_REVIEW" | "FAILED"
