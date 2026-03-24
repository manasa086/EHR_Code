"""
Tests for Claude integration paths in ai_service:
- Successful Claude response is parsed and returned
- Timeout / network error → falls back to rule-based
- Invalid JSON from Claude → falls back to rule-based
- Missing API key → RuntimeError raised
- Confidence score clamping to 0.0–1.0

Claude functions now take only raw request_data — no rule-based pre-assessment is passed.
The rule-based result is used only as a silent fallback when Claude fails entirely.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services.ai_service import (
    _claude_enhance,
    _claude_enhance_quality,
    reconcile_medication,
    validate_data_quality,
)

RECONCILE_DATA = {
    "patient_context": {
        "age": 66,
        "conditions": ["Atrial Fibrillation"],
        "recent_labs": {"INR": 1.8},
    },
    "sources": [
        {"system": "Hospital EHR",  "medication": "Warfarin 5mg",   "last_updated": "2025-01-10", "source_reliability": "high"},
        {"system": "Cardiology",    "medication": "Warfarin 7.5mg", "last_updated": "2025-02-18", "source_reliability": "high"},
        {"system": "Pharmacy",      "medication": "Warfarin 5mg",   "last_filled":  "2025-03-01", "source_reliability": "medium"},
    ],
}

# Used only as a base for building Claude reply dicts in tests — not passed to Claude functions
CLAUDE_RECONCILE_REPLY = {
    "reconciled_medication": "Warfarin 7.5mg",
    "confidence_score": 0.75,
    "reasoning": "Most recent high-reliability source.",
    "recommended_actions": ["Confirm with patient"],
    "clinical_safety_check": "PASSED",
}

QUALITY_DATA = {
    "demographics": {"name": "Jane", "dob": "1980-01-01", "gender": "F"},
    "medications": ["Metformin 500mg"],
    "allergies": [],
    "conditions": ["Type 2 Diabetes"],
    "vital_signs": {"blood_pressure": "130/80", "heart_rate": 78},
    "last_updated": "2025-01-01",
}

# Used only as a base for building Claude reply dicts in tests — not passed to Claude functions
CLAUDE_QUALITY_REPLY = {
    "overall_score": 72,
    "breakdown": {"completeness": 80, "accuracy": 100, "timeliness": 65, "clinical_plausibility": 80},
    "issues_detected": [],
    "summary": "Record is mostly complete with good accuracy.",
}


def make_mock_response(body: dict) -> MagicMock:
    """Build a fake httpx response that returns body as JSON."""
    mock = MagicMock()
    mock.json.return_value = {
        "content": [{"type": "text", "text": json.dumps(body)}]
    }
    mock.raise_for_status = MagicMock()
    return mock


# ── _claude_enhance ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claude_enhance_returns_parsed_result():
    claude_reply = {
        "reconciled_medication": "Warfarin 5mg",
        "confidence_score": 0.62,
        "reasoning": "Pharmacy fill is most recent actual dispensing data.",
        "recommended_actions": ["Check INR immediately"],
        "clinical_safety_check": "NEEDS_REVIEW",
    }
    mock_response = make_mock_response(claude_reply)

    with patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await _claude_enhance(RECONCILE_DATA)

    assert result["reconciled_medication"] == "Warfarin 5mg"
    assert result["confidence_score"] == 0.62
    assert result["clinical_safety_check"] == "NEEDS_REVIEW"


@pytest.mark.asyncio
async def test_claude_enhance_clamps_confidence_score_above_1():
    claude_reply = {**CLAUDE_RECONCILE_REPLY, "confidence_score": 1.5}
    mock_response = make_mock_response(claude_reply)

    with patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await _claude_enhance(RECONCILE_DATA)

    assert result["confidence_score"] <= 1.0


@pytest.mark.asyncio
async def test_claude_enhance_clamps_confidence_score_below_0():
    claude_reply = {**CLAUDE_RECONCILE_REPLY, "confidence_score": -0.5}
    mock_response = make_mock_response(claude_reply)

    with patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await _claude_enhance(RECONCILE_DATA)

    assert result["confidence_score"] >= 0.0


@pytest.mark.asyncio
async def test_claude_enhance_raises_without_api_key():
    with patch("services.ai_service.os.getenv", return_value=""):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            await _claude_enhance(RECONCILE_DATA)


@pytest.mark.asyncio
async def test_claude_enhance_raises_on_invalid_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"content": [{"type": "text", "text": "not valid json {{{"}]}
    mock_response.raise_for_status = MagicMock()

    with patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(Exception):
            await _claude_enhance(RECONCILE_DATA)


# ── reconcile_medication (public interface) ───────────────────────────────────

@pytest.mark.asyncio
async def test_reconcile_medication_uses_mock_when_flag_is_true():
    with patch("services.ai_service.USE_MOCK", True):
        result = await reconcile_medication(RECONCILE_DATA)
    assert "reconciled_medication" in result
    assert "confidence_score" in result


@pytest.mark.asyncio
async def test_reconcile_medication_calls_claude_when_mock_is_false():
    claude_reply = {**CLAUDE_RECONCILE_REPLY, "confidence_score": 0.55}
    mock_response = make_mock_response(claude_reply)

    with patch("services.ai_service.USE_MOCK", False), \
         patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await reconcile_medication(RECONCILE_DATA)

    assert result["confidence_score"] == 0.55


@pytest.mark.asyncio
async def test_reconcile_medication_falls_back_on_timeout():
    with patch("services.ai_service.USE_MOCK", False), \
         patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock,
               side_effect=httpx.ReadTimeout("")):
        result = await reconcile_medication(RECONCILE_DATA)

    # Should still return a valid rule-based result
    assert "reconciled_medication" in result
    assert "confidence_score" in result


@pytest.mark.asyncio
async def test_reconcile_medication_falls_back_on_generic_exception():
    with patch("services.ai_service.USE_MOCK", False), \
         patch("services.ai_service._claude_enhance", new_callable=AsyncMock,
               side_effect=Exception("unexpected error")):
        result = await reconcile_medication(RECONCILE_DATA)

    assert "reconciled_medication" in result


# ── _claude_enhance_quality ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claude_enhance_quality_returns_parsed_result():
    claude_reply = {
        "overall_score": 68,
        "breakdown": {"completeness": 70, "accuracy": 90, "timeliness": 55, "clinical_plausibility": 75},
        "issues_detected": [{"field": "allergies", "issue": "Empty allergy list", "severity": "medium"}],
        "summary": "Record is moderately complete but allergy documentation is missing.",
    }
    mock_response = make_mock_response(claude_reply)

    with patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await _claude_enhance_quality(QUALITY_DATA)

    assert result["overall_score"] == 68
    assert result["summary"] == "Record is moderately complete but allergy documentation is missing."
    assert len(result["issues_detected"]) == 1


@pytest.mark.asyncio
async def test_claude_enhance_quality_raises_without_api_key():
    with patch("services.ai_service.os.getenv", return_value=""):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            await _claude_enhance_quality(QUALITY_DATA)


# ── validate_data_quality (public interface) ──────────────────────────────────

@pytest.mark.asyncio
async def test_validate_data_quality_uses_mock_when_flag_is_true():
    with patch("services.ai_service.USE_MOCK", True):
        result = await validate_data_quality(QUALITY_DATA)
    assert "overall_score" in result
    assert 0 <= result["overall_score"] <= 100


@pytest.mark.asyncio
async def test_validate_data_quality_falls_back_on_timeout():
    with patch("services.ai_service.USE_MOCK", False), \
         patch("services.ai_service.os.getenv", return_value="test-api-key"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock,
               side_effect=httpx.ReadTimeout("")):
        result = await validate_data_quality(QUALITY_DATA)

    assert "overall_score" in result
    assert "breakdown" in result
