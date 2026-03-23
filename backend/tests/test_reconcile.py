from services.ai_service import _mock_reconcile


def make_request(sources, age=60, conditions=None, labs=None):
    return {
        "patient_context": {
            "age": age,
            "conditions": conditions or [],
            "recent_labs": labs or {},
        },
        "sources": sources,
    }


def test_picks_most_recent_high_reliability_source():
    result = _mock_reconcile(make_request([
        {"system": "Hospital EHR",  "medication": "Metformin 1000mg", "last_updated": "2024-01-01", "source_reliability": "high"},
        {"system": "Primary Care",  "medication": "Metformin 500mg",  "last_updated": "2025-01-20", "source_reliability": "high"},
        {"system": "Pharmacy",      "medication": "Metformin 1000mg", "last_updated": "2025-01-25", "source_reliability": "medium"},
    ]))
    # Primary Care: high reliability × recent date beats Pharmacy medium reliability × slightly more recent
    assert result["reconciled_medication"] == "Metformin 500mg"


def test_confidence_score_is_within_valid_range():
    result = _mock_reconcile(make_request([
        {"system": "Clinic", "medication": "Aspirin 81mg", "last_updated": "2025-01-01", "source_reliability": "high"},
    ]))
    assert 0.0 <= result["confidence_score"] <= 1.0


def test_safety_check_flags_metformin_with_very_low_egfr():
    result = _mock_reconcile(make_request(
        sources=[{"system": "Clinic", "medication": "Metformin 1000mg", "last_updated": "2025-01-01", "source_reliability": "high"}],
        labs={"eGFR": 25},
    ))
    assert result["clinical_safety_check"] == "NEEDS_REVIEW"
    assert any("eGFR" in a or "contraindicated" in a.lower() for a in result["recommended_actions"])


def test_safety_check_passes_for_non_renal_medication():
    result = _mock_reconcile(make_request([
        {"system": "Clinic", "medication": "Lisinopril 10mg", "last_updated": "2025-01-01", "source_reliability": "high"},
    ]))
    assert result["clinical_safety_check"] == "PASSED"


def test_response_contains_all_required_fields():
    result = _mock_reconcile(make_request([
        {"system": "Clinic", "medication": "Aspirin 81mg", "last_updated": "2025-01-01", "source_reliability": "high"},
    ]))
    required = ["reconciled_medication", "confidence_score", "reasoning", "recommended_actions", "clinical_safety_check"]
    for field in required:
        assert field in result, f"Missing field: {field}"
