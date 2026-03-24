"""
AI service — currently uses rule-based mocks.
To switch to real Claude: set USE_MOCK_AI=false in .env and implement
_claude_reconcile / _claude_data_quality below.
"""
import os
import json
from datetime import datetime
from typing import Optional
import httpx

from prompts import RECONCILIATION_SYSTEM_PROMPT, DATA_QUALITY_SYSTEM_PROMPT

USE_MOCK = os.getenv("USE_MOCK_AI", "true").lower() == "true"

RELIABILITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ["%Y-%m-%d", "%Y/%m/%d"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


# ── mock: medication reconciliation ──────────────────────────────────────────

def _mock_reconcile(request_data: dict) -> dict:
    sources = request_data["sources"]

    # Score each source by recency × reliability
    def score(s):
        date = _parse_date(s.get("last_updated") or s.get("last_filled"))
        date_score = date.timestamp() if date else 0
        reliability = RELIABILITY_WEIGHT.get(s.get("source_reliability", "low"), 1)
        return date_score * reliability

    ranked = sorted(sources, key=score, reverse=True)
    best = ranked[0]

    # Confidence: higher when sources agree
    unique_meds = {s["medication"] for s in sources}
    if len(unique_meds) == 1:
        base_confidence = 0.95
    elif len(unique_meds) == 2:
        base_confidence = 0.85
    else:
        base_confidence = 0.75

    # Build reasoning
    best_date = best.get("last_updated") or best.get("last_filled") or "unknown date"
    reasoning = (
        f"'{best['system']}' is the most authoritative source "
        f"(date: {best_date}, reliability: {best.get('source_reliability', 'unknown')}). "
    )
    if len(unique_meds) > 1:
        reasoning += f"{len(unique_meds)} conflicting entries found — reconciled to most recent high-reliability record. "
    else:
        reasoning += "All sources agree on this medication. "

    # Recommended actions
    actions = ["Confirm medication with patient at next clinical visit"]
    conflicting = [s["system"] for s in sources if s["medication"] != best["medication"]]
    for system in conflicting:
        actions.append(f"Update {system} record to: {best['medication']}")

    # Safety check — the rule-based engine cannot perform accurate clinical safety
    # assessments. recent_labs can contain any lab values (e.g. "INR", "eGFR",
    # "Anion Gap", "Bicarbonate", "Glucose", "Ionized Ca", "Chloride", and many
    # others). Medication names are also not normalised across systems. Hardcoding
    # checks for any specific lab key or drug name would silently miss every other
    # combination and produce misleading PASSED results for cases it cannot handle.
    # This result is a fallback only (returned when Claude is unavailable).
    # Real safety assessment — across all lab values and all medications — is
    # performed exclusively by Claude from the raw patient data.
    safety = "NEEDS_REVIEW"

    return {
        "reconciled_medication": best["medication"],
        "confidence_score": round(min(0.98, base_confidence), 2),
        "reasoning": reasoning.strip(),
        "recommended_actions": actions,
        "clinical_safety_check": safety,
    }


# ── mock: data quality validation ─────────────────────────────────────────────

def _mock_data_quality(request_data: dict) -> dict:
    issues = []

    # --- Completeness ---
    completeness = 100
    demographics = request_data.get("demographics") or {}
    for field in ["name", "dob", "gender"]:
        if not demographics.get(field):
            completeness -= 10
            issues.append({
                "field": f"demographics.{field}",
                "issue": f"'{field}' is missing from demographics",
                "severity": "medium",
            })

    if not request_data.get("medications"):
        completeness -= 10
        issues.append({"field": "medications", "issue": "No medications documented", "severity": "medium"})

    allergies = request_data.get("allergies")
    if allergies is None:
        completeness -= 10
        issues.append({"field": "allergies", "issue": "Allergy field is absent", "severity": "medium"})
    elif len(allergies) == 0:
        completeness -= 10
        issues.append({"field": "allergies", "issue": "No allergies documented — likely incomplete", "severity": "medium"})

    if not request_data.get("conditions"):
        completeness -= 10
        issues.append({"field": "conditions", "issue": "No conditions documented", "severity": "medium"})

    if not request_data.get("vital_signs"):
        completeness -= 10
        issues.append({"field": "vital_signs", "issue": "No vital signs documented", "severity": "medium"})

    completeness = max(0, completeness)

    # --- Accuracy ---
    accuracy = 100
    vitals = request_data.get("vital_signs") or {}
    bp_str = vitals.get("blood_pressure")

    if bp_str:
        try:
            systolic, diastolic = map(int, bp_str.split("/"))
            if systolic > 300 or diastolic > 200:
                accuracy -= 50
                issues.append({
                    "field": "vital_signs.blood_pressure",
                    "issue": f"Blood pressure {bp_str} is physiologically implausible",
                    "severity": "high",
                })
            elif systolic < 60 or diastolic < 30:
                accuracy -= 30
                issues.append({
                    "field": "vital_signs.blood_pressure",
                    "issue": f"Blood pressure {bp_str} is abnormally low",
                    "severity": "high",
                })
        except (ValueError, AttributeError):
            accuracy -= 20
            issues.append({
                "field": "vital_signs.blood_pressure",
                "issue": "Blood pressure format is invalid (expected systolic/diastolic)",
                "severity": "medium",
            })

    hr = vitals.get("heart_rate")
    if hr is not None and (hr < 20 or hr > 300):
        accuracy -= 30
        issues.append({
            "field": "vital_signs.heart_rate",
            "issue": f"Heart rate {hr} bpm is physiologically implausible",
            "severity": "high",
        })

    # --- Duplicate source systems ---
    sources = request_data.get("sources") or []
    systems = [s.get("system", "").strip().lower() for s in sources if s.get("system")]
    seen, duplicates = set(), set()
    for sys in systems:
        if sys in seen:
            duplicates.add(sys)
        seen.add(sys)
    for dup in duplicates:
        accuracy -= 25
        issues.append({
            "field": "sources",
            "issue": f"System '{dup}' appears more than once — possible duplicate record entry",
            "severity": "high",
        })

    accuracy = max(0, accuracy)

    # --- Timeliness ---
    timeliness = 100
    last_updated = request_data.get("last_updated")

    if last_updated:
        try:
            updated = datetime.strptime(last_updated, "%Y-%m-%d")
            months_old = (datetime.now() - updated).days / 30
            if months_old > 12:
                timeliness = 40
                issues.append({
                    "field": "last_updated",
                    "issue": f"Data is {int(months_old)} months old",
                    "severity": "high",
                })
            elif months_old > 6:
                timeliness = 65
                issues.append({
                    "field": "last_updated",
                    "issue": f"Data is {int(months_old)} months old",
                    "severity": "medium",
                })
            elif months_old > 3:
                timeliness = 80
        except ValueError:
            timeliness = 50
    else:
        timeliness = 30
        issues.append({"field": "last_updated", "issue": "No last updated date provided", "severity": "medium"})

    # --- Clinical Plausibility ---
    # The rule-based engine cannot assess clinical plausibility accurately.
    # Conditions can be anything — "Atrial Fibrillation", "CKD", "COPD",
    # "Hypothyroidism", "Depression", etc. — each requiring different expected
    # medications. Hardcoding checks for any specific condition/medication pair
    # would silently score every other combination as 100 (falsely plausible).
    # This result is a fallback only (returned when Claude is unavailable).
    # Real clinical plausibility assessment — across all conditions and medications
    # — is performed exclusively by Claude from the raw patient record.
    clinical_plausibility = 50

    overall = int((completeness + accuracy + timeliness + clinical_plausibility) / 4)

    return {
        "overall_score": overall,
        "breakdown": {
            "completeness": completeness,
            "accuracy": accuracy,
            "timeliness": timeliness,
            "clinical_plausibility": clinical_plausibility,
        },
        "issues_detected": issues,
    }


# ── Claude: enhance rule-based result with clinical reasoning ─────────────────

async def _claude_enhance(request_data: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when USE_MOCK_AI=false")
    print("[ai_service] Calling Anthropic Claude API...")

    system_prompt = RECONCILIATION_SYSTEM_PROMPT

    # Send only raw patient data — no rule-based pre-assessment.
    # Rule-based output is kept as a silent fallback only (used if Claude fails entirely).
    # Sending rule-based results would anchor Claude to hardcoded rules that assume
    # specific lab names and medication patterns, producing wrong results for other cases.
    user_message = json.dumps({"patient_data": request_data}, indent=2)

    print("[ai_service] Input data:", user_message)

    payload = {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": 2000,
        "temperature": 0,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    print("[ai_service] Claude raw response:", response.json())

    text_blocks = [
        block.get("text", "")
        for block in response.json().get("content", [])
        if block.get("type") == "text"
    ]
    content = "".join(text_blocks).strip()
    print("[ai_service] Claude extracted text:", content)

    # Extract JSON even if Claude wraps it in markdown
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1:
        content = content[start:end + 1]

    print("[ai_service] Claude JSON to parse:", content)
    parsed = json.loads(content)
    print("[ai_service] Claude parsed result:", parsed)
    confidence = float(parsed["confidence_score"])

    return {
        "reconciled_medication": str(parsed["reconciled_medication"]),
        "confidence_score": round(max(0.0, min(1.0, confidence)), 2),
        "reasoning": str(parsed["reasoning"]),
        "recommended_actions": [str(x) for x in parsed["recommended_actions"]],
        "clinical_safety_check": str(parsed["clinical_safety_check"]),
    }


# ── public interface called by routers ───────────────────────────────────────

async def reconcile_medication(request_data: dict) -> dict:
    # Step 1: rule-based engine always runs first
    rule_based = _mock_reconcile(request_data)

    # Step 2: mock-only mode — return rule-based result as-is
    if USE_MOCK:
        return rule_based

    # Step 3: pass raw data + rule-based pre-assessment to Claude
    # If Claude fails for any reason, fall back to the rule-based result
    try:
        return await _claude_enhance(request_data)
    except Exception as e:
        import traceback
        print(f"[ai_service] Claude enhance failed, falling back to rule-based.")
        print(f"  Exception type : {type(e).__name__}")
        print(f"  Exception repr : {repr(e)}")
        print(f"  Traceback      :\n{traceback.format_exc()}")
        return rule_based


async def _claude_enhance_quality(request_data: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when USE_MOCK_AI=false")

    print("[ai_service] Calling Anthropic Claude API for data quality...")

    system_prompt = DATA_QUALITY_SYSTEM_PROMPT

    # Send only raw patient record — no rule-based pre-assessment.
    # Rule-based output is kept as a silent fallback only (used if Claude fails entirely).
    # Sending rule-based scores would anchor Claude to hardcoded rules that cannot
    # generalise across cases with different fields and clinical profiles.
    user_message = json.dumps({"patient_record": request_data}, indent=2)

    print("[ai_service] Input data:", user_message)

    payload = {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": 2000,
        "temperature": 0,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    print("[ai_service] Claude quality raw response:", response.json())

    text_blocks = [
        block.get("text", "")
        for block in response.json().get("content", [])
        if block.get("type") == "text"
    ]
    content = "".join(text_blocks).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1:
        content = content[start:end + 1]

    print("[ai_service] Claude quality JSON to parse:", content)
    parsed = json.loads(content)
    print("[ai_service] Claude quality parsed result:", parsed)

    return {
        "overall_score": int(parsed["overall_score"]),
        "breakdown": {
            "completeness":          int(parsed["breakdown"]["completeness"]),
            "accuracy":              int(parsed["breakdown"]["accuracy"]),
            "timeliness":            int(parsed["breakdown"]["timeliness"]),
            "clinical_plausibility": int(parsed["breakdown"]["clinical_plausibility"]),
        },
        "issues_detected": parsed["issues_detected"],
        "summary": parsed["summary"],
    }


async def validate_data_quality(request_data: dict) -> dict:
    # Step 1: rule-based engine always runs first
    rule_based = _mock_data_quality(request_data)

    # Step 2: mock-only mode — return rule-based result as-is
    if USE_MOCK:
        return rule_based

    # Step 3: enhance with Claude; fall back to rule-based on any failure
    try:
        return await _claude_enhance_quality(request_data)
    except Exception as e:
        import traceback
        print(f"[ai_service] Claude quality enhance failed, falling back to rule-based.")
        print(f"  Exception type : {type(e).__name__}")
        print(f"  Exception repr : {repr(e)}")
        print(f"  Traceback      :\n{traceback.format_exc()}")
        return rule_based
