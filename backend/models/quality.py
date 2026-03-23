from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class Demographics(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None


class VitalSigns(BaseModel):
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None


class DataQualityRequest(BaseModel):
    # Core quality fields
    demographics: Optional[Demographics] = None
    medications: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    conditions: Optional[List[str]] = None
    vital_signs: Optional[VitalSigns] = None
    last_updated: Optional[str] = None
    # Full case metadata — included so the cache key covers every case field
    id: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    patient_context: Optional[Dict[str, Any]] = None
    sources: Optional[List[Dict[str, Any]]] = None


class ScoreBreakdown(BaseModel):
    completeness: int
    accuracy: int
    timeliness: int
    clinical_plausibility: int


class Issue(BaseModel):
    field: str
    issue: str
    severity: str  # "low" | "medium" | "high"


class DataQualityResponse(BaseModel):
    overall_score: int
    breakdown: ScoreBreakdown
    issues_detected: List[Issue]
    summary: Optional[str] = None
