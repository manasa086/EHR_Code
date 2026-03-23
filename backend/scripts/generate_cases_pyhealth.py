"""
generate_cases_pyhealth.py
==========================
Uses PyHealth's OMOPDataset to load the OMOP CSV files, then converts
the raw numeric concept IDs into readable patient cases and writes
sample_cases.json.

Run from the backend/ directory:
    pip install pyhealth pandas
    python scripts/generate_cases_pyhealth.py

What PyHealth gives you vs what we still need to do manually is explained
step by step in the comments below.
"""

import json
import os
import sys

# ── 1. Check PyHealth is installed ──────────────────────────────────────────
try:
    from pyhealth.datasets import OMOPDataset
except ImportError:
    print("PyHealth not installed. Run:  pip install pyhealth pandas")
    sys.exit(1)

import pandas as pd

# ── 2. Paths ─────────────────────────────────────────────────────────────────
OMOP_DIR   = os.path.join(os.path.dirname(__file__), "..", "data", "omop")
OUTPUT     = os.path.join(os.path.dirname(__file__), "..", "data", "sample_cases.json")

# ── 3. ICD → readable name mapping ───────────────────────────────────────────
#
# PyHealth loads the OMOP tables and gives you concept IDs (numbers).
# To get human-readable names you need EITHER:
#   a) The full OMOP vocabulary (~20 GB from athena.ohdsi.org)
#   b) The condition_source_value column, which contains the original ICD code
#      the hospital submitted before it was mapped to an OMOP concept ID.
#
# We use approach (b): read condition_source_value → look up ICD code below.
# Any ICD code not in this dict will print as "Unknown (ICD: <code>)".

ICD_MAP = {
    # ICD-9 codes (no dot notation in source values)
    "2724":  "Type 2 Diabetes Mellitus",
    "25000": "Diabetes Mellitus without complications",
    "25050": "Diabetes with ophthalmic complications",
    "41401": "Coronary Artery Disease",
    "42731": "Atrial Fibrillation",
    "42732": "Atrial Fibrillation",
    "4239":  "Atrial Flutter",
    "4019":  "Essential Hypertension",
    "4111":  "Unstable Angina",
    "5859":  "Chronic Kidney Disease",
    "40390": "Hypertensive Chronic Kidney Disease",
    "36201": "Diabetic Retinopathy",
    "2859":  "Anemia, unspecified",
    "2536":  "Thyroid disorder",
    "04109": "Post-surgical complication",
    "04119": "Abdominal condition",
    "04185": "GI complication",
    "56981": "Intestinal obstruction / Ileus",
    "56722": "Peptic ulcer",
    "56989": "GI disorder",
    "570":   "Acute liver disease",
    "5720":  "Hepatic encephalopathy",
    "5601":  "Intestinal obstruction",
    "20190": "Lymphoma / Hematologic malignancy",
    "49390": "Asthma, unspecified",
    "3968":  "Fluid/electrolyte disorder",
    "33520": "Carpal tunnel syndrome",
    "72402": "Spinal stenosis",
    "1978":  "Secondary malignant neoplasm",
    "1560":  "Cholangiocarcinoma",
    "5845":  "Acute Kidney Injury",
    "34690": "Abdominal hernia",
    "53081": "Esophageal reflux",
    "28749": "Coagulation defect",
    "2749":  "Other lipid storage disorder",
    "5641":  "Irritable bowel syndrome",
    "4779":  "Disorders of fluid/electrolyte",
    "E8782": "Injury due to medical device",
    "E8788": "Injury, other",
    "99859": "Post-operative complication",
    "99749": "Complication of medical care",
    "2639":  "Nutritional deficiency",
    "7837":  "Cachexia",
    # ICD-10 codes
    "I214":  "Acute anterior STEMI",
    "K219":  "GERD",
    "I7102": "Peripheral Arterial Disease",
    "I509":  "Heart Failure, unspecified",
    "J9811": "Pulmonary edema",
    "I319":  "Pericardial disease / Atrial flutter",
    "E875":  "Hyperkalemia",
    "D649":  "Anemia, unspecified",
    "E46":   "Malnutrition",
    "J918":  "Pleural effusion",
    "G40909":"Epilepsy, unspecified",
    "J189":  "Pneumonia, unspecified",
    "R21":   "Rash",
    "H540":  "Visual impairment",
    "R001":  "Bradycardia",
    "D688":  "Coagulopathy",
    "I314":  "Pericardial disease",
    "I313":  "Pericarditis",
    "78062": "Hypoxia",
    "440372":"Traumatic injury",
    # Literal string in source data
    "SVT (Supra Ventricular Tachycardia)": "Supraventricular Tachycardia",
}

# ── 4. Measurement concept ID → lab name ─────────────────────────────────────
#
# PyHealth exposes measurement_concept_id. These are OMOP standard LOINC codes.
# Without the vocabulary we use a small local lookup for the IDs in our dataset.

MEASUREMENT_MAP = {
    3012501: ("Anion Gap",    "mEq/L"),
    3031147: ("Bicarbonate",  "mEq/L"),
    3018572: ("Chloride",     "mEq/L"),
    3021119: ("Ionized Ca",   "mmol/L"),
    3000483: ("Glucose",      "mg/dL"),
}

# ── 5. Medication conflicts (designed per patient condition profile) ───────────
#
# PyHealth gives us drug_concept_id (RxNorm/NDC), not drug names.
# Decoding those also needs the vocabulary. So we assign clinically realistic
# medication conflicts based on each patient's condition list.
# A real system would join drug_concept_id against the OMOP concept table.

MEDICATION_CONFLICTS = {
    # person_id (str) → list of 3 source dicts
    "3589912774911670296": [   # SVT + DM + CAD patient
        {"system": "Hospital EHR",     "medication": "Metoprolol 25mg twice daily",    "last_updated": "2025-01-18", "source_reliability": "high"},
        {"system": "Cardiology Clinic","medication": "Diltiazem 120mg daily",           "last_updated": "2025-02-05", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Metoprolol 50mg twice daily",     "last_filled":  "2025-02-10", "source_reliability": "medium"},
    ],
    "-3210373572193940939": [  # AF + DM + HTN patient
        {"system": "Hospital EHR",     "medication": "Rivaroxaban 20mg daily",          "last_updated": "2025-01-05", "source_reliability": "high"},
        {"system": "Primary Care",     "medication": "Apixaban 5mg twice daily",        "last_updated": "2025-02-14", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Rivaroxaban 15mg daily",          "last_filled":  "2025-02-20", "source_reliability": "medium"},
    ],
    "-775517641933593374": [   # Cardiac + Liver patient
        {"system": "Emergency Room",   "medication": "Azithromycin 500mg daily x5d",   "last_updated": "2025-03-10", "source_reliability": "high"},
        {"system": "Primary Care",     "medication": "Amoxicillin-Clavulanate 875mg bid x7d","last_updated":"2025-03-12","source_reliability":"high"},
        {"system": "Pharmacy",         "medication": "Azithromycin 500mg daily",        "last_filled":  "2025-03-10", "source_reliability": "medium"},
    ],
    "-2575767131279873665": [  # DM + CKD patient
        {"system": "Hospital EHR",     "medication": "Metformin 1000mg twice daily",    "last_updated": "2024-10-15", "source_reliability": "high"},
        {"system": "Primary Care",     "medication": "Metformin 500mg twice daily",     "last_updated": "2025-01-20", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Metformin 1000mg daily",          "last_filled":  "2025-01-25", "source_reliability": "medium"},
    ],
    "-8970844422700220177": [  # Hypertensive patient
        {"system": "Primary Care",     "medication": "Amlodipine 5mg daily",            "last_updated": "2025-02-01", "source_reliability": "high"},
        {"system": "Internal Medicine","medication": "Amlodipine 10mg daily",            "last_updated": "2025-02-28", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Amlodipine 5mg daily",             "last_filled": "2025-02-05", "source_reliability": "medium"},
    ],
    "4668337230155062633": [   # GI surgery patient
        {"system": "Surgery EHR",      "medication": "Oxycodone 5mg every 6h PRN",      "last_updated": "2025-03-08", "source_reliability": "high"},
        {"system": "Primary Care",     "medication": "Tramadol 50mg every 8h PRN",      "last_updated": "2025-03-02", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Oxycodone 10mg every 6h PRN",     "last_filled":  "2025-03-09", "source_reliability": "medium"},
    ],
    "2631971469928551627": [   # Young hypertensive
        {"system": "Primary Care",     "medication": "Lisinopril 5mg daily",             "last_updated": "2025-02-12", "source_reliability": "high"},
        {"system": "Internal Medicine","medication": "Lisinopril 10mg daily",            "last_updated": "2025-03-01", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Lisinopril 5mg daily",             "last_filled":  "2025-02-15", "source_reliability": "medium"},
    ],
    "8692405834444096922": [   # Post-MI + PAD patient
        {"system": "Cardiology Clinic","medication": "Aspirin 81mg + Ticagrelor 90mg bid","last_updated":"2025-03-01","source_reliability":"high"},
        {"system": "Primary Care",     "medication": "Aspirin 81mg + Clopidogrel 75mg daily","last_updated":"2025-02-10","source_reliability":"high"},
        {"system": "Pharmacy",         "medication": "Aspirin 81mg + Clopidogrel 75mg daily","last_filled":"2025-03-05","source_reliability":"medium"},
    ],
    "-4873075614181207858": [  # AF + CAD + Pacemaker patient
        {"system": "Hospital EHR",     "medication": "Warfarin 5mg daily",               "last_updated": "2025-01-10", "source_reliability": "high"},
        {"system": "Cardiology Clinic","medication": "Warfarin 7.5mg daily",              "last_updated": "2025-02-18", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Warfarin 5mg daily",               "last_filled":  "2025-03-01", "source_reliability": "medium"},
    ],
    "-5829006308524050971": [  # Heart Failure + Epilepsy patient
        {"system": "Hospital EHR",     "medication": "Furosemide 80mg IV daily",         "last_updated": "2025-02-22", "source_reliability": "high"},
        {"system": "Primary Care",     "medication": "Furosemide 40mg oral daily",       "last_updated": "2025-01-30", "source_reliability": "high"},
        {"system": "Pharmacy",         "medication": "Torsemide 20mg oral daily",        "last_filled":  "2025-02-01", "source_reliability": "medium"},
    ],
}

# ── 6. Static patient names (no real PII — positional fake names) ─────────────
PATIENT_NAMES = [
    "Patient A", "Patient B", "Patient C", "Patient D", "Patient E",
    "Patient F", "Patient G", "Patient H", "Patient I", "Patient J",
]

# ── 7. Allergies per patient condition profile ────────────────────────────────
#
# Keyed by person_id (str). Clinically realistic given each patient's
# conditions and medications.

PATIENT_ALLERGIES = {
    "3589912774911670296": ["Sulfonamides", "Contrast Dye"],           # SVT + DM + CAD
    "-3210373572193940939": ["Aspirin", "NSAIDs"],                     # AF + DM + HTN
    "-775517641933593374":  ["Penicillin", "Codeine"],                 # Cardiac + Liver
    "-2575767131279873665": ["Sulfonamides", "Iodine"],                # DM + CKD
    "-8970844422700220177": ["ACE Inhibitors", "Latex"],               # Hypertensive
    "4668337230155062633":  ["Morphine", "Cephalosporins"],            # GI surgery
    "2631971469928551627":  ["Penicillin", "Sulfonamides"],            # Young hypertensive
    "8692405834444096922":  ["Heparin", "Ibuprofen"],                  # Post-MI + PAD
    "-4873075614181207858": ["Aspirin", "Iodine Contrast"],            # AF + CAD + Pacemaker
    "-5829006308524050971": ["Carbamazepine", "Penicillin"],           # Heart Failure + Epilepsy
}

# ── 8. Vital signs per patient condition profile ──────────────────────────────
#
# Clinically realistic vitals keyed by person_id (str).

PATIENT_VITALS = {
    "3589912774911670296": {"blood_pressure": "128/82", "heart_rate": 88},   # SVT + DM + CAD
    "-3210373572193940939": {"blood_pressure": "145/90", "heart_rate": 78},  # AF + DM + HTN
    "-775517641933593374":  {"blood_pressure": "110/70", "heart_rate": 102}, # Cardiac + Liver
    "-2575767131279873665": {"blood_pressure": "138/86", "heart_rate": 74},  # DM + CKD
    "-8970844422700220177": {"blood_pressure": "158/96", "heart_rate": 80},  # Hypertensive
    "4668337230155062633":  {"blood_pressure": "122/78", "heart_rate": 95},  # GI surgery
    "2631971469928551627":  {"blood_pressure": "148/92", "heart_rate": 76},  # Young hypertensive
    "8692405834444096922":  {"blood_pressure": "132/84", "heart_rate": 68},  # Post-MI + PAD
    "-4873075614181207858": {"blood_pressure": "130/85", "heart_rate": 72},  # AF + CAD + Pacemaker
    "-5829006308524050971": {"blood_pressure": "115/72", "heart_rate": 58},  # Heart Failure + Epilepsy
}


def decode_condition(source_value: str) -> str:
    """Map an ICD code or literal string to a readable condition name."""
    key = source_value.strip()
    return ICD_MAP.get(key, f"Unknown (ICD: {key})")


def get_age(year_of_birth: int, visit_year: int) -> int:
    return visit_year - year_of_birth


def build_dob(year_of_birth, month_of_birth, day_of_birth, visit_year: int) -> str:
    """
    Build a DOB string in YYYY-MM-DD format.

    The OMOP synthetic data uses futuristic birth years (e.g. 2095).
    We normalise by computing the real birth year as:
        real_birth_year = visit_year - (synthetic_birth_year - visit_year_in_dataset)
    But a simpler and more faithful approach is to just back-calculate the
    real birth year from the age already computed:
        real_birth_year = <calendar year of visit> - age_at_visit
    We already compute age = visit_year - synthetic_year_of_birth which gives
    a negative number when the synthetic year is in the future.  To produce a
    plausible real DOB we anchor the year to 2025 minus that same age offset.
    """
    try:
        yob = int(year_of_birth)
        mob = int(month_of_birth) if pd.notna(month_of_birth) else 1
        dob_day = int(day_of_birth) if pd.notna(day_of_birth) else 1
        # Normalise futuristic synthetic birth year to a realistic past year
        # by computing the age offset against visit_year and subtracting from 2025
        age_offset = visit_year - yob
        real_birth_year = 2025 - abs(age_offset)
        return f"{real_birth_year:04d}-{mob:02d}-{dob_day:02d}"
    except (ValueError, TypeError):
        return "1960-01-01"


def get_last_updated(sources: list) -> str:
    """Return the most recent date found in any source's last_updated or last_filled field."""
    dates = []
    for src in sources:
        for key in ("last_updated", "last_filled"):
            val = src.get(key)
            if val:
                dates.append(val)
    return max(dates) if dates else "2025-01-01"


def main():
    # ── Step A: Load with PyHealth OMOPDataset ────────────────────────────────
    #
    # PyHealth reads all OMOP tables from the folder and builds a structured
    # patient → visit → events hierarchy.
    #
    # What PyHealth returns for conditions:
    #   event.code  →  the condition_concept_id  (e.g. "432867")  ← OMOP number
    #
    # What PyHealth returns for drugs:
    #   event.code  →  the drug_concept_id  (e.g. "19078557")  ← OMOP number
    #
    # In both cases the number is meaningless without the OMOP vocabulary.
    # That is the fundamental limitation this script works around.

    print("Loading OMOP data with PyHealth OMOPDataset...")
    print(f"  Source folder: {OMOP_DIR}\n")

    import warnings
    warnings.filterwarnings("ignore")

    dataset = OMOPDataset(
        root=OMOP_DIR,
        tables=["condition_occurrence", "drug_exposure", "measurement"],
        code_mapping={},   # no vocabulary — we will handle decoding ourselves
        dev=False,
    )

    print(f"PyHealth loaded {len(dataset.patients)} patients.")
    print()
    print("NOTE: PyHealth 1.1.6 has a bug in parse_condition_occurrence —")
    print("  condition_unit() builds Event objects but has no 'return events'.")
    print("  Result: get_code_list(table='condition_occurrence') returns [] for all patients.")
    print("  Drug and measurement events work correctly (those parsers do return events).")
    print("  Workaround: we read condition_source_value directly via pandas below.\n")

    # ── Step B: Also load raw CSVs with pandas to get source values ───────────
    #
    # PyHealth stores condition_concept_id (OMOP number) as event.code.
    # The original ICD code is in condition_source_value.
    # We join the raw CSV to recover it.

    # Files are now TSV (tab-separated) — PyHealth requires this format
    person_df    = pd.read_csv(os.path.join(OMOP_DIR, "person.csv"),              sep="\t", dtype={"person_id": str})
    cond_df      = pd.read_csv(os.path.join(OMOP_DIR, "condition_occurrence.csv"), sep="\t", dtype={"person_id": str})
    measure_df   = pd.read_csv(os.path.join(OMOP_DIR, "measurement.csv"),          sep="\t", dtype={"person_id": str})

    # Build lookup: person_id → birth info dict
    person_info = {}
    for _, row in person_df.iterrows():
        pid = str(row["person_id"])
        person_info[pid] = {
            "year_of_birth":  row.get("year_of_birth"),
            "month_of_birth": row.get("month_of_birth"),
            "day_of_birth":   row.get("day_of_birth"),
            "gender_concept_id": row.get("gender_concept_id"),
        }

    # Build lookup: person_id → year_of_birth (kept for age calculation)
    person_birth = {pid: info["year_of_birth"] for pid, info in person_info.items()}

    # Build lookup: person_id → list of ICD source values (unique)
    cond_sources = (
        cond_df.groupby("person_id")["condition_source_value"]
        .apply(lambda x: list(x.dropna().unique()))
        .to_dict()
    )
    cond_sources = {str(k): v for k, v in cond_sources.items()}

    # Build lookup: person_id → dict of {lab_name: value}
    measure_df = measure_df[measure_df["measurement_concept_id"].isin(MEASUREMENT_MAP)]
    labs_by_patient = {}
    for pid, group in measure_df.groupby("person_id"):
        labs = {}
        for _, row in group.iterrows():
            concept_id = int(row["measurement_concept_id"])
            if concept_id in MEASUREMENT_MAP:
                lab_name, unit = MEASUREMENT_MAP[concept_id]
                value = row.get("value_as_number")
                if pd.notna(value) and value > 0:
                    labs[lab_name] = round(float(value), 2)
        if labs:
            labs_by_patient[str(pid)] = labs

    # ── Step C: Walk PyHealth patients and build cases ────────────────────────
    print("=" * 60)
    print("RAW OUTPUT FROM PyHealth (what it gives before mapping):")
    print("=" * 60)

    cases = []
    case_num = 1

    for patient_id, patient in dataset.patients.items():
        pid_str = str(patient_id)

        # Skip test rows (person_id 1, 2 — synthetic, no real data)
        if pid_str in ("1", "2"):
            continue

        # Skip patients with no condition data
        if pid_str not in cond_sources or not cond_sources[pid_str]:
            continue

        # PyHealth patient object — show raw data first
        print(f"\nPatient ID : {patient_id}")
        print(f"  Visits   : {len(patient.visits)}")

        # Get first visit to show raw concept IDs from PyHealth
        first_visit = next(iter(patient.visits.values()), None)
        if first_visit:
            raw_conditions = first_visit.get_code_list(table="condition_occurrence")
            raw_drugs      = first_visit.get_code_list(table="drug_exposure")
            print(f"  Raw condition concept IDs (from PyHealth): {raw_conditions[:5]}")
            print(f"  Raw drug concept IDs      (from PyHealth): {raw_drugs[:5]}")

        # ── Now decode using source values (the point of this script) ────────

        # Age: use birth year and earliest visit encounter_time
        # PyHealth Visit uses: encounter_time (start) and discharge_time (end)
        birth_year = person_birth.get(pid_str)
        visit_years = [
            v.encounter_time.year
            for v in patient.visits.values()
            if v.encounter_time is not None
        ]
        visit_year = min(visit_years) if visit_years else 2025
        age = get_age(int(birth_year), visit_year) if birth_year else "Unknown"

        # Conditions: decode ICD source values
        icd_codes   = cond_sources.get(pid_str, [])
        conditions  = []
        for code in icd_codes:
            name = decode_condition(str(code))
            if not name.startswith("Unknown") and name not in conditions:
                conditions.append(name)

        if not conditions:
            print(f"  -> Skipping: no decodable conditions")
            continue

        # Labs from measurement.csv
        labs = labs_by_patient.get(pid_str, {})

        # Medication sources (designed per patient profile)
        sources = MEDICATION_CONFLICTS.get(pid_str)
        if not sources:
            print(f"  -> Skipping: no medication conflict defined")
            continue

        # ── Demographics: name, dob, gender ──────────────────────────────────
        name_index = (case_num - 1) % len(PATIENT_NAMES)
        patient_name = PATIENT_NAMES[name_index]

        pinfo = person_info.get(pid_str, {})
        dob = build_dob(
            pinfo.get("year_of_birth"),
            pinfo.get("month_of_birth"),
            pinfo.get("day_of_birth"),
            visit_year,
        )

        gender_concept_id = pinfo.get("gender_concept_id")
        if pd.notna(gender_concept_id) if gender_concept_id is not None else False:
            gender = "M" if int(float(gender_concept_id)) == 8507 else "F"
        else:
            gender = "Unknown"

        demographics = {
            "name":   patient_name,
            "dob":    dob,
            "gender": gender,
        }

        # ── Allergies and vital signs ─────────────────────────────────────────
        allergies   = PATIENT_ALLERGIES.get(pid_str, ["NKDA"])
        vital_signs = PATIENT_VITALS.get(pid_str, {"blood_pressure": "120/80", "heart_rate": 72})

        # ── last_updated: most recent date across all sources ─────────────────
        last_updated = get_last_updated(sources)

        # Build label and description
        primary_condition = conditions[0]
        label = f"Case {case_num:03d} — {primary_condition} Patient"
        description = (
            f"{age}-year-old patient with {', '.join(conditions[:3])}. "
            f"Conflicting medication records across {len(sources)} systems."
        )

        case = {
            "id": f"case_{case_num:03d}",
            "label": label,
            "description": description,
            "patient_context": {
                "age": age,
                "conditions": conditions[:5],      # cap at 5 for readability
                "recent_labs": labs if labs else {"eGFR": 75},
            },
            "sources": sources,
            "demographics": demographics,
            "allergies": allergies,
            "vital_signs": vital_signs,
            "last_updated": last_updated,
        }

        cases.append(case)
        print(f"  -> Built case_{case_num:03d}: {label}")
        case_num += 1

    # ── Step D: Write sample_cases.json ──────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Writing {len(cases)} cases to {OUTPUT}")
    print("=" * 60)

    with open(OUTPUT, "w") as f:
        json.dump(cases, f, indent=2)

    print("\nDone. sample_cases.json updated.")
    print("Restart the backend to serve the new cases via GET /api/cases")


if __name__ == "__main__":
    main()
