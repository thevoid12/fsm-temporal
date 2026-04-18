"""
Mock External Service — simulates unmodified external APIs that the engine's
adapter/worker calls. Uses standard HTTP status codes for pass/fail.

2xx = success, 4xx/5xx = failure. The adapter translates the HTTP status
into a callback to the engine. No engine-specific conventions needed.

Run: make mock
"""

import asyncio

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Mock External Service", version="0.1.0")

call_counts: dict[str, int] = {}


class TaskPayload(BaseModel):
    """Incoming payload from the FSM activity."""
    state_id: str
    workflow_id: str


@app.post("/task/instant-success")
async def instant_success(payload: TaskPayload):
    """Returns 200. Tests the happy path."""
    return {"message": "CRF validated successfully"}


@app.post("/task/instant-fail")
async def instant_fail(payload: TaskPayload):
    """Returns 422. Tests retry/exhaustion."""
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed: missing required fields"},
    )


@app.post("/task/slow-success")
async def slow_success(payload: TaskPayload):
    """Waits 15 seconds then returns 200. Tests slow external APIs."""
    await asyncio.sleep(15)
    return {"message": "Processing complete"}


@app.post("/task/timeout")
async def timeout_endpoint(payload: TaskPayload):
    """Sleeps 60 seconds (longer than dispatch timeout). Tests timeout handling."""
    await asyncio.sleep(60)
    return {"message": "This should never be reached"}


@app.post("/task/fail-then-succeed")
async def fail_then_succeed(payload: TaskPayload):
    """Returns 500 on first call, 200 on second. Tests retry recovery."""
    key = f"{payload.workflow_id}:{payload.state_id}"
    call_counts[key] = call_counts.get(key, 0) + 1

    if call_counts[key] <= 1:
        return JSONResponse(status_code=500, content={"error": "Transient error"})
    return {"message": "Succeeded on retry"}


# ==============================================================================
# Conditional transition test endpoints
# ==============================================================================


@app.post("/task/return-approved")
async def return_approved(payload: TaskPayload):
    """Returns 200 with status=approved. Tests equals operator."""
    return {"status": "approved"}


@app.post("/task/return-tags")
async def return_tags(payload: TaskPayload):
    """Returns 200 with a tags string. Tests contains operator."""
    return {"tags": "urgent,critical,review"}


@app.post("/task/return-with-field")
async def return_with_field(payload: TaskPayload):
    """Returns 200 with approval_id present. Tests exists operator."""
    return {"approval_id": "abc-123", "message": "approved"}


@app.post("/task/return-no-error")
async def return_no_error(payload: TaskPayload):
    """Returns 200 without an error field. Tests not_exists operator."""
    return {"message": "all clear"}


@app.post("/task/return-422")
async def return_422(payload: TaskPayload):
    """Returns 422 with error body. Tests status_code_range 4xx operator."""
    return JSONResponse(status_code=422, content={"error": "validation_failed"})


@app.post("/task/return-pending")
async def return_pending(payload: TaskPayload):
    """Returns 200 with result=pending. Tests not_equals operator."""
    return {"result": "pending"}


@app.post("/task/return-500")
async def return_500(payload: TaskPayload):
    """Returns 500 with error body. Tests status_code_range 5xx with no matching condition (stay in state)."""
    return JSONResponse(status_code=500, content={"error": "server_error"})


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}
