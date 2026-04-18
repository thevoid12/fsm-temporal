"""Temporal activities for the FSM engine.
Handles HTTP calls to task callback endpoints defined in the workflow JSON.
"""

import httpx
from temporalio import activity

from config import load_config
from models import (
    HttpMethod,
    TaskCallbackHttpRequest,
    TaskCallbackInput,
    TaskCallbackLogContext,
    TaskCallbackRequestBody,
    TaskCallbackResult,
)

logger = activity.logger

METHODS_WITH_BODY = {HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH}


@activity.defn
async def execute_task_callback(input: TaskCallbackInput) -> TaskCallbackResult:
    """Call the task callback URL. Returns result for all HTTP responses; only network errors raise for Temporal retry."""
    body_data = TaskCallbackRequestBody(
        state_id=input.state_id,
        workflow_id=input.workflow_id,
    ).model_dump()

    # For HTTP methods like POST, PUT, PATCH - the data goes in the request body as JSON (json=).
    # For GET and DELETE: there's no request body, so the data goes as query parameters in the URL (params=),
    # e.g. ?state_id=state-1&workflow_id=abc.
    if input.http_method in METHODS_WITH_BODY:
        http_request = TaskCallbackHttpRequest(json_body=body_data)
    else:
        http_request = TaskCallbackHttpRequest(query_params=body_data)

    log_ctx = TaskCallbackLogContext(
        callback_url=input.callback_url,
        state_id=input.state_id,
        workflow_id=input.workflow_id,
    )

    logger.info("Executing task callback", extra=log_ctx.model_dump(exclude_none=True))

    config = load_config()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.http_client.timeout_seconds)) as client:
            response = await client.request(
                input.http_method.value,
                input.callback_url,
                **http_request.to_httpx_kwargs(),
            )
    except httpx.HTTPError as e:
        log_ctx.error = str(e)
        logger.error("HTTP request failed", extra=log_ctx.model_dump(exclude_none=True))
        raise RuntimeError(f"HTTP request to {input.callback_url} failed: {e}") from e

    log_ctx.status_code = response.status_code

    if response.is_success:
        logger.info("Task callback succeeded", extra=log_ctx.model_dump(exclude_none=True))
    else:
        log_ctx.body = response.text
        logger.warning("Task callback returned non-2xx status", extra=log_ctx.model_dump(exclude_none=True))

    return TaskCallbackResult(
        success=response.is_success,
        status_code=response.status_code,
        body=response.text,
    )
