from fastapi import APIRouter, Depends
from models.medication import ReconcileRequest, ReconcileResponse
from services.ai_service import reconcile_medication
from services.cache_service import cache
from services.sse_service import broadcaster
from middleware.auth import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/reconcile/medication", response_model=ReconcileResponse)
async def reconcile_medication_endpoint(request: ReconcileRequest):
    request_dict = request.model_dump()

    cached = cache.get(request_dict)
    if cached:
        print("[reconcile] Cache hit — skipping API call")
        await broadcaster.broadcast("reconciliation_done", {
            "case_id": request_dict.get("id"),
            "label":   request_dict.get("label"),
            "result":  cached,
            "cached":  True,
        })
        return cached

    try:
        result = await reconcile_medication(request_dict)
        cache.set(request_dict, result)
    except Exception as e:
        print(f"[reconcile] Claude call failed: {e}")
        cached = cache.get(request_dict)
        if cached:
            result = cached
        else:
            from services.ai_service import _mock_reconcile
            result = _mock_reconcile(request_dict)

    await broadcaster.broadcast("reconciliation_done", {
        "case_id": request_dict.get("id"),
        "label":   request_dict.get("label"),
        "result":  result,
        "cached":  False,
    })
    return result
