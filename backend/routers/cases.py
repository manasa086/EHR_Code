import json
import os
from fastapi import APIRouter, Depends, HTTPException
from middleware.auth import verify_api_key
from services.sse_service import broadcaster

router = APIRouter(dependencies=[Depends(verify_api_key)])

_DATA_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
# USER_DATA_DIR env var lets Docker point this at a named volume (/app/userdata)
# so user_cases.json never touches the host filesystem.
# Falls back to the data/ folder for local development.
_USER_DATA_DIR = os.environ.get("USER_DATA_DIR", _DATA_DIR)
os.makedirs(_USER_DATA_DIR, exist_ok=True)

SAMPLE_FILE = os.path.join(_DATA_DIR,     "sample_cases.json")
USER_FILE   = os.path.join(_USER_DATA_DIR, "user_cases.json")


def _read_sample():
    with open(SAMPLE_FILE) as f:
        cases = json.load(f)
    for c in cases:
        c["editable"] = False
    return cases


def _read_user():
    if not os.path.exists(USER_FILE):
        return []
    with open(USER_FILE) as f:
        return json.load(f)


def _write_user(cases):
    with open(USER_FILE, "w") as f:
        json.dump(cases, f, indent=2)


@router.get("/cases")
def list_cases():
    return _read_sample() + _read_user()


def _content_key(c: dict) -> str:
    """Canonical key for duplicate content detection — ignores id/editable."""
    return json.dumps(
        {
            "label": (c.get("label") or "").strip().lower(),
            "patient_context": c.get("patient_context"),
            "sources": c.get("sources"),
        },
        sort_keys=True,
        default=str,
    )


@router.post("/cases")
async def create_case(body: dict):
    user_cases = _read_user()
    sample_cases = _read_sample()

    # Reject if another case already has the same clinical content
    new_key = _content_key(body)
    for existing in sample_cases + user_cases:
        if _content_key(existing) == new_key:
            raise HTTPException(
                status_code=409,
                detail=f"A case with identical content already exists: {existing['id']}",
            )

    all_ids = {c["id"] for c in sample_cases} | {c["id"] for c in user_cases}
    n = len(sample_cases) + len(user_cases) + 1
    new_id = f"case_{n:03d}"
    while new_id in all_ids:
        n += 1
        new_id = f"case_{n:03d}"
    body["id"] = new_id
    body["editable"] = True
    user_cases.append(body)
    _write_user(user_cases)
    await broadcaster.broadcast("case_created", body)
    return body


@router.put("/cases/{case_id}")
async def update_case(case_id: str, body: dict):
    user_cases = _read_user()
    for i, c in enumerate(user_cases):
        if c["id"] == case_id:
            body["id"] = case_id
            body["editable"] = True
            user_cases[i] = body
            _write_user(user_cases)
            await broadcaster.broadcast("case_updated", body)
            return body
    # Check if it's a default case and reject
    if any(c["id"] == case_id for c in _read_sample()):
        raise HTTPException(status_code=403, detail="Default cases cannot be edited")
    raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
