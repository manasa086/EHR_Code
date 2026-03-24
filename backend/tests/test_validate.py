from services.ai_service import _mock_data_quality


def complete_record(**overrides):
    base = {
        "demographics": {"name": "Jane Doe", "dob": "1980-06-15", "gender": "F"},
        "medications": ["Aspirin 81mg", "Lisinopril 10mg"],
        "allergies": ["Penicillin"],
        "conditions": ["Hypertension"],
        "vital_signs": {"blood_pressure": "120/80", "heart_rate": 72},
        "last_updated": "2025-06-01",
    }
    base.update(overrides)
    return base


def test_detects_implausible_blood_pressure():
    result = _mock_data_quality(complete_record(
        vital_signs={"blood_pressure": "340/180", "heart_rate": 72}
    ))
    flagged_fields = [i["field"] for i in result["issues_detected"]]
    assert "vital_signs.blood_pressure" in flagged_fields


def test_overall_score_is_within_valid_range():
    result = _mock_data_quality(complete_record())
    assert 0 <= result["overall_score"] <= 100


def test_detects_empty_allergies_as_incomplete():
    result = _mock_data_quality(complete_record(allergies=[]))
    flagged_fields = [i["field"] for i in result["issues_detected"]]
    assert "allergies" in flagged_fields


def test_breakdown_contains_all_four_dimensions():
    result = _mock_data_quality(complete_record())
    expected = {"completeness", "accuracy", "timeliness", "clinical_plausibility"}
    assert expected == set(result["breakdown"].keys())


def test_complete_recent_record_scores_above_70():
    result = _mock_data_quality(complete_record(last_updated="2025-10-01"))
    assert result["overall_score"] >= 70


def test_clinical_plausibility_is_neutral_in_fallback():
    # The rule-based fallback cannot assess clinical plausibility across
    # arbitrary conditions and medications, so it always returns 50 (neutral).
    # Real clinical plausibility scoring is done exclusively by Claude.
    result = _mock_data_quality(complete_record())
    assert result["breakdown"]["clinical_plausibility"] == 50
