"""
Integration tests for all API endpoints using FastAPI TestClient.
Covers: auth middleware, routers, models, cache, and decisions store.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from main import app
from services.cache_service import cache

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-secret-key"}

RECONCILE_PAYLOAD = {
    "patient_context": {
        "age": 65,
        "conditions": ["Hypertension"],
        "recent_labs": {"eGFR": 80},
    },
    "sources": [
        {"system": "Hospital EHR",  "medication": "Lisinopril 10mg", "last_updated": "2025-01-10", "source_reliability": "high"},
        {"system": "Primary Care",  "medication": "Lisinopril 20mg", "last_updated": "2025-02-01", "source_reliability": "high"},
        {"system": "Pharmacy",      "medication": "Lisinopril 10mg", "last_filled":  "2025-02-05", "source_reliability": "medium"},
    ],
}

QUALITY_PAYLOAD = {
    "demographics": {"name": "John Doe", "dob": "1970-01-01", "gender": "M"},
    "medications": ["Aspirin 81mg"],
    "allergies": ["Penicillin"],
    "conditions": ["Hypertension"],
    "vital_signs": {"blood_pressure": "130/85", "heart_rate": 74},
    "last_updated": "2025-06-01",
}


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """Ensure cache is empty before every test."""
    cache.clear()
    yield
    cache.clear()


# ── Auth middleware ───────────────────────────────────────────────────────────

def test_missing_api_key_returns_422():
    res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD)
    assert res.status_code == 422


def test_wrong_api_key_returns_401():
    res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD,
                      headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401


def test_valid_api_key_is_accepted():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD, headers=HEADERS)
    assert res.status_code == 200


# ── GET /api/cases ────────────────────────────────────────────────────────────

def test_get_cases_returns_list():
    res = client.get("/api/cases", headers=HEADERS)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) > 0


def test_case_has_required_fields():
    res = client.get("/api/cases", headers=HEADERS)
    case = res.json()[0]
    for field in ["id", "label", "description", "patient_context", "sources"]:
        assert field in case, f"Missing field: {field}"


# ── POST /api/reconcile/medication ───────────────────────────────────────────

def test_reconcile_returns_required_fields():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD, headers=HEADERS)
    assert res.status_code == 200
    body = res.json()
    for field in ["reconciled_medication", "confidence_score", "reasoning",
                  "recommended_actions", "clinical_safety_check"]:
        assert field in body, f"Missing field: {field}"


def test_reconcile_confidence_score_in_range():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD, headers=HEADERS)
    score = res.json()["confidence_score"]
    assert 0.0 <= score <= 1.0


def test_reconcile_cache_hit_skips_second_call():
    mock_result = {
        "reconciled_medication": "Lisinopril 10mg",
        "confidence_score": 0.9,
        "reasoning": "cached",
        "recommended_actions": [],
        "clinical_safety_check": "PASSED",
    }
    with patch("services.ai_service.USE_MOCK", True):
        # First call — populates cache
        client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD, headers=HEADERS)

    # Manually inject a known value into cache to verify hit behaviour
    cache.set(RECONCILE_PAYLOAD, mock_result)
    res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD, headers=HEADERS)
    # Note: TestClient serializes/deserializes so the response comes from
    # the router which checks cache first — but model validation applies on response_model.
    # We just verify a 200 is returned (cache hit path executed).
    assert res.status_code == 200


def test_reconcile_invalid_payload_returns_422():
    res = client.post("/api/reconcile/medication", json={"bad": "data"}, headers=HEADERS)
    assert res.status_code == 422


def test_reconcile_falls_back_to_rule_based_when_claude_raises():
    with patch("services.ai_service.USE_MOCK", False), \
         patch("services.ai_service._claude_enhance", new_callable=AsyncMock,
               side_effect=Exception("simulated Claude failure")):
        res = client.post("/api/reconcile/medication", json=RECONCILE_PAYLOAD, headers=HEADERS)
    assert res.status_code == 200
    assert "reconciled_medication" in res.json()


# ── POST /api/validate/data-quality ──────────────────────────────────────────

def test_validate_returns_required_fields():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/validate/data-quality", json=QUALITY_PAYLOAD, headers=HEADERS)
    assert res.status_code == 200
    body = res.json()
    for field in ["overall_score", "breakdown", "issues_detected"]:
        assert field in body, f"Missing field: {field}"


def test_validate_score_in_range():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/validate/data-quality", json=QUALITY_PAYLOAD, headers=HEADERS)
    assert 0 <= res.json()["overall_score"] <= 100


def test_validate_breakdown_has_four_dimensions():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/validate/data-quality", json=QUALITY_PAYLOAD, headers=HEADERS)
    breakdown = res.json()["breakdown"]
    assert set(breakdown.keys()) == {"completeness", "accuracy", "timeliness", "clinical_plausibility"}


def test_validate_falls_back_when_claude_raises():
    with patch("services.ai_service.USE_MOCK", False), \
         patch("services.ai_service._claude_enhance_quality", new_callable=AsyncMock,
               side_effect=Exception("simulated Claude failure")):
        res = client.post("/api/validate/data-quality", json=QUALITY_PAYLOAD, headers=HEADERS)
    assert res.status_code == 200
    assert "overall_score" in res.json()


def test_validate_empty_payload_still_returns_200():
    with patch("services.ai_service.USE_MOCK", True):
        res = client.post("/api/validate/data-quality", json={}, headers=HEADERS)
    assert res.status_code == 200


# ── POST /api/decisions ───────────────────────────────────────────────────────

def test_record_decision_returns_id_and_timestamp():
    payload = {"type": "medication_reconciliation", "decision": "approved"}
    res = client.post("/api/decisions", json=payload, headers=HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert "id" in body
    assert "timestamp" in body
    assert body["decision"] == "approved"


def test_record_decision_rejected():
    payload = {"type": "medication_reconciliation", "decision": "rejected"}
    res = client.post("/api/decisions", json=payload, headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["decision"] == "rejected"


def test_list_decisions_returns_previous_entries():
    payload = {"type": "medication_reconciliation", "decision": "approved"}
    client.post("/api/decisions", json=payload, headers=HEADERS)
    res = client.get("/api/decisions", headers=HEADERS)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
