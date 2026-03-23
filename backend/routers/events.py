"""
GET /api/events  — Server-Sent Events endpoint.

Browsers connect once and receive a persistent stream of named events.
EventSource does not support custom headers, so the API key is passed
as a query parameter instead.

Named SSE events emitted:
  connected            — sent once on successful connection
  heartbeat            — sent every 25 s to keep the connection alive
  reconciliation_done  — AI reconciliation finished for a case
  data_quality_done    — data quality validation finished for a case
  case_created         — a new user case was added
  case_updated         — an existing user case was edited
  decision_recorded    — a clinician approved or rejected a result
"""
import asyncio
import os

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from services.sse_service import broadcaster

router = APIRouter()


@router.get("/events")
async def event_stream(
    request: Request,
    api_key: str = Query(..., alias="api_key"),
):
    expected = os.getenv("API_KEY", "dev-secret-key")
    if api_key != expected:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid API key")

    async def generate():
        queue = broadcaster.subscribe()
        try:
            # Confirm connection
            yield "event: connected\ndata: {}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"event: {event}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive ping — browsers and proxies drop idle SSE connections
                    yield "event: heartbeat\ndata: {}\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # prevent nginx from buffering the stream
            "Connection":      "keep-alive",
        },
    )
