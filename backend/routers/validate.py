from fastapi import APIRouter, Depends
from models.quality import DataQualityRequest, DataQualityResponse
from services.ai_service import validate_data_quality
from services.cache_service import cache
from services.sse_service import broadcaster
from middleware.auth import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/validate/data-quality", response_model=DataQualityResponse)
async def validate_data_quality_endpoint(request: DataQualityRequest):
    request_dict = request.model_dump()

    cached = cache.get(request_dict)
    if cached:
        await broadcaster.broadcast("data_quality_done", {
            "case_id": request_dict.get("id"),
            "label":   request_dict.get("label"),
            "result":  cached,
            "cached":  True,
        })
        return cached

    result = await validate_data_quality(request_dict)
    cache.set(request_dict, result)

    await broadcaster.broadcast("data_quality_done", {
        "case_id": request_dict.get("id"),
        "label":   request_dict.get("label"),
        "result":  result,
        "cached":  False,
    })
    return result
