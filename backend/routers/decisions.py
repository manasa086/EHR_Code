import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from typing import Optional
from models.decision import DecisionRequest, DecisionResponse
from services.sse_service import broadcaster
from middleware.auth import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

decisions_store: list = []


@router.post("/decisions", response_model=DecisionResponse)
async def record_decision(request: DecisionRequest):
    entry = {
        "id":        str(uuid.uuid4()),
        "type":      request.type,
        "decision":  request.decision,
        "case_id":   request.case_id,
        "notes":     request.notes,
        "data":      request.data,
        "timestamp": datetime.now().isoformat(),
    }
    decisions_store.append(entry)
    await broadcaster.broadcast("decision_recorded", entry)
    return entry


@router.get("/decisions")
async def list_decisions(
    case_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
):
    results = decisions_store
    if case_id:
        results = [d for d in results if d.get("case_id") == case_id]
    if type:
        results = [d for d in results if d.get("type") == type]
    return results
