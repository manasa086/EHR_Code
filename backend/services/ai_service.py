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
    patient = request_data["patient_context"]

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

    # Safety check using patient context
    safety = "PASSED"
    egfr = (patient.get("recent_labs") or {}).get("eGFR")

    if egfr and "metformin" in best["medication"].lower():
        if egfr < 30:
            safety = "NEEDS_REVIEW"
            base_confidence -= 0.10
            actions.append("Metformin contraindicated with eGFR < 30 — consult prescriber immediately")
        elif egfr <= 45:
            reasoning += f"Patient eGFR {egfr} — dose reduction may be warranted; verify with prescriber."
            actions.append("Verify Metformin dose is appropriate given eGFR level")

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
    clinical_plausibility = 100
    conditions = [c.lower() for c in (request_data.get("conditions") or [])]
    meds = [m.lower() for m in (request_data.get("medications") or [])]

    diabetes_meds = ["metformin", "insulin", "glipizide", "jardiance", "ozempic", "glimepiride"]
    if "type 2 diabetes" in conditions:
        if not any(dm in m for dm in diabetes_meds for m in meds):
            clinical_plausibility -= 20
            issues.append({
                "field": "medications",
                "issue": "Type 2 Diabetes diagnosed but no diabetes medications listed",
                "severity": "medium",
            })

    hypertension_meds = ["lisinopril", "amlodipine", "metoprolol", "losartan", "hydrochlorothiazide"]
    if "hypertension" in conditions:
        if not any(hm in m for hm in hypertension_meds for m in meds):
            clinical_plausibility -= 15
            issues.append({
                "field": "medications",
                "issue": "Hypertension diagnosed but no antihypertensive medications listed",
                "severity": "medium",
            })

    clinical_plausibility = max(0, clinical_plausibility)

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

async def _claude_enhance(request_data: dict, rule_based: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when USE_MOCK_AI=false")
    print("[ai_service] Calling Anthropic Claude API...")
    print("[ai_service] Input data:", json.dumps({
        "patient_data": request_data,
        "rule_based_pre_assessment": {k: v for k, v in rule_based.items() if k != "confidence_score"},
    }, indent=2))

    system_prompt = RECONCILIATION_SYSTEM_PROMPT

    # Strip confidence_score so Claude determines it independently
    rule_based_without_score = {k: v for k, v in rule_based.items() if k != "confidence_score"}

    user_message = json.dumps({
        "patient_data": request_data,
        "rule_based_pre_assessment": rule_based_without_score,
    }, indent=2)

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
    confidence = float(parsed.get("confidence_score", rule_based["confidence_score"]))

    return {
        "reconciled_medication": str(parsed.get("reconciled_medication", rule_based["reconciled_medication"])),
        "confidence_score": round(max(0.0, min(1.0, confidence)), 2),
        "reasoning": str(parsed.get("reasoning", rule_based["reasoning"])),
        "recommended_actions": [str(x) for x in parsed.get("recommended_actions", rule_based["recommended_actions"])],
        "clinical_safety_check": str(parsed.get("clinical_safety_check", rule_based["clinical_safety_check"])),
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
        return await _claude_enhance(request_data, rule_based)
    except Exception as e:
        import traceback
        print(f"[ai_service] Claude enhance failed, falling back to rule-based.")
        print(f"  Exception type : {type(e).__name__}")
        print(f"  Exception repr : {repr(e)}")
        print(f"  Traceback      :\n{traceback.format_exc()}")
        return rule_based


async def _claude_enhance_quality(request_data: dict, rule_based: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when USE_MOCK_AI=false")

    print("[ai_service] Calling Anthropic Claude API for data quality...")
    print("[ai_service] Input data:", json.dumps({
        "patient_record": request_data,
        "rule_based_pre_assessment": {k: v for k, v in rule_based.items() if k != "overall_score"},
    }, indent=2))

    system_prompt = DATA_QUALITY_SYSTEM_PROMPT

    rule_based_without_score = {k: v for k, v in rule_based.items() if k != "overall_score"}

    user_message = json.dumps({
        "patient_record": request_data,
        "rule_based_pre_assessment": rule_based_without_score,
    }, indent=2)

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
        "overall_score": int(parsed.get("overall_score", rule_based["overall_score"])),
        "breakdown": {
            "completeness":          int(parsed.get("breakdown", {}).get("completeness",          rule_based["breakdown"]["completeness"])),
            "accuracy":              int(parsed.get("breakdown", {}).get("accuracy",              rule_based["breakdown"]["accuracy"])),
            "timeliness":            int(parsed.get("breakdown", {}).get("timeliness",            rule_based["breakdown"]["timeliness"])),
            "clinical_plausibility": int(parsed.get("breakdown", {}).get("clinical_plausibility", rule_based["breakdown"]["clinical_plausibility"])),
        },
        "issues_detected": parsed.get("issues_detected", rule_based["issues_detected"]),
        "summary": parsed.get("summary", ""),
    }


async def validate_data_quality(request_data: dict) -> dict:
    # Step 1: rule-based engine always runs first
    rule_based = _mock_data_quality(request_data)

    # Step 2: mock-only mode — return rule-based result as-is
    if USE_MOCK:
        return rule_based

    # Step 3: enhance with Claude; fall back to rule-based on any failure
    try:
        return await _claude_enhance_quality(request_data, rule_based)
    except Exception as e:
        import traceback
        print(f"[ai_service] Claude quality enhance failed, falling back to rule-based.")
        print(f"  Exception type : {type(e).__name__}")
        print(f"  Exception repr : {repr(e)}")
        print(f"  Traceback      :\n{traceback.format_exc()}")
        return rule_based
