"""FastAPI API server bridging the custom written workflow configuration UI to Temporal workflows and filesystem-based templates.
Handles template CRUD on workflow_definitions/ and runtime operations via Temporal client.
"""

import json
import logging
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from config import load_config
from models import (
    QUERY_AUDIT_TRAIL,
    QUERY_AVAILABLE_TRANSITIONS,
    QUERY_CURRENT_STATE,
    SIGNAL_NAME,
    WORKFLOW_NAME,
    StartWorkflowRequest,
    TemplateSummary,
    TransitionRequest,
    ValidationCheck,
    ValidationResult,
    WorkflowDefinition,
)

logger = logging.getLogger(__name__)

config = load_config()
definitions_dir = Path(config.api_server.workflow_definitions_dir)
definitions_dir.mkdir(exist_ok=True)

app = FastAPI(title="Temporal FSM API")

temporal_client: Client | None = None


@app.on_event("startup")
async def startup() -> None:
    """Connect to Temporal server on app startup.
    using fastapi and establishing grpc connection to temporal server"""
    global temporal_client
    temporal_client = await Client.connect(
        config.temporal.server_address,
        data_converter=pydantic_data_converter,
    )
    logger.info("Connected to Temporal at %s", config.temporal.server_address)


def _get_temporal_client() -> Client:
    """Return the cached Temporal client, raising if not connected."""
    if temporal_client is None:
        raise HTTPException(status_code=503, detail="Temporal client not connected")
    return temporal_client


# ==============================================================================
# Template endpoints (filesystem CRUD)
# ==============================================================================


def _template_path(template_id: str) -> Path:
    """Resolve the JSON file path for a template ID."""
    return definitions_dir / f"{template_id}.json"


def _ui_metadata_path(template_id: str) -> Path:
    """Resolve the UI metadata file path for a template ID."""
    return definitions_dir / f"{template_id}.ui.json"


def _read_template(template_id: str) -> dict:
    """Read and parse a template JSON file, raising 404 if missing."""
    path = _template_path(template_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    with open(path) as f:
        return json.load(f)


def _write_template(template_id: str, data: dict) -> None:
    """Write a template dict to its JSON file, stripping any UI metadata."""
    data.pop("id", None)
    for state in data.get("states", []):
        state.pop("metadata", None)
    path = _template_path(template_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _read_ui_metadata(template_id: str) -> dict:
    """Read UI node positions. Returns empty dict if file doesn't exist."""
    path = _ui_metadata_path(template_id)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _write_ui_metadata(template_id: str, data: dict) -> None:
    """Write UI node positions to a separate metadata file."""
    path = _ui_metadata_path(template_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


@app.get("/api/v1/templates")
async def list_templates() -> list[TemplateSummary]:
    """List all workflow templates from the definitions directory."""
    templates = []
    for path in sorted(definitions_dir.glob("*.json")):
        if path.name.endswith(".ui.json"):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            templates.append(TemplateSummary(
                id=path.stem,
                name=data.get("name", path.stem),
                description=data.get("description", ""),
            ))
        except (json.JSONDecodeError, KeyError):
            logger.warning("Skipping invalid template file: %s", path)
    return templates


@app.post("/api/v1/templates")
async def create_template(body: dict) -> TemplateSummary:
    """Create a new template from a name or full workflow JSON."""
    if "states" in body:
        template_id = body.get("name", "unnamed").replace(" ", "-").lower()
        if _template_path(template_id).exists():
            template_id = f"{template_id}-{uuid.uuid4().hex[:6]}"
        _write_template(template_id, body)
    else:
        name = body.get("name", "unnamed")
        template_id = name.strip().replace(" ", "-").lower()
        if _template_path(template_id).exists():
            template_id = f"{template_id}-{uuid.uuid4().hex[:6]}"
        _write_template(template_id, {
            "name": name,
            "description": body.get("description", ""),
            "states": [],
            "transitions": [],
        })
    data = _read_template(template_id)
    return TemplateSummary(
        id=template_id,
        name=data.get("name", template_id),
        description=data.get("description", ""),
    )


@app.get("/api/v1/templates/{template_id}")
async def get_template(template_id: str) -> dict:
    """Read a template JSON file. Serves as both detail and export."""
    data = _read_template(template_id)
    data["id"] = template_id
    return data


@app.put("/api/v1/templates/{template_id}")
async def update_template(template_id: str, body: dict) -> dict:
    """Overwrite a template JSON file with new data from the builder."""
    if not _template_path(template_id).exists():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    body.pop("id", None)
    _write_template(template_id, body)
    data = _read_template(template_id)
    data["id"] = template_id
    return data


@app.delete("/api/v1/templates/{template_id}")
async def delete_template(template_id: str) -> dict:
    """Delete a template and its UI metadata file from disk."""
    path = _template_path(template_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    path.unlink()
    ui_path = _ui_metadata_path(template_id)
    if ui_path.exists():
        ui_path.unlink()
    return {"deleted": template_id}


@app.get("/api/v1/templates/{template_id}/ui-metadata")
async def get_ui_metadata(template_id: str) -> dict:
    """Read UI node positions for a template."""
    if not _template_path(template_id).exists():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return _read_ui_metadata(template_id)


@app.put("/api/v1/templates/{template_id}/ui-metadata")
async def update_ui_metadata(template_id: str, body: dict) -> dict:
    """Save UI node positions for a template."""
    if not _template_path(template_id).exists():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    _write_ui_metadata(template_id, body)
    return body


@app.post("/api/v1/templates/{template_id}/validate")
async def validate_template(template_id: str) -> ValidationResult:
    """Run structural validation checks on a template."""
    data = _read_template(template_id)
    checks: list[ValidationCheck] = []

    # Check 1: Valid JSON that parses as WorkflowDefinition
    try:
        wf = WorkflowDefinition.model_validate(data)
        checks.append(ValidationCheck(check="Valid WorkflowDefinition schema", passed=True))
    except Exception as e:
        checks.append(ValidationCheck(check="Valid WorkflowDefinition schema", passed=False, details=str(e)))
        return ValidationResult(valid=False, checks=checks)

    # Check 2: Exactly one start state
    start_states = [s for s in wf.states if s.is_start]
    checks.append(ValidationCheck(
        check="Exactly one start state",
        passed=len(start_states) == 1,
        details=f"Found {len(start_states)}" if len(start_states) != 1 else None,
    ))

    # Check 3: At least one end state
    end_states = [s for s in wf.states if s.is_end]
    checks.append(ValidationCheck(
        check="At least one end state",
        passed=len(end_states) >= 1,
        details=f"Found {len(end_states)}" if len(end_states) < 1 else None,
    ))

    # Check 4: All transition source/target refs valid
    state_ids = {s.unique_identifier for s in wf.states}
    invalid_refs = []
    for t in wf.transitions:
        if t.source_state not in state_ids:
            invalid_refs.append(f"{t.unique_identifier}: source '{t.source_state}' not found")
        if t.target_state not in state_ids:
            invalid_refs.append(f"{t.unique_identifier}: target '{t.target_state}' not found")
    checks.append(ValidationCheck(
        check="All transition refs valid",
        passed=len(invalid_refs) == 0,
        details="; ".join(invalid_refs) if invalid_refs else None,
    ))

    # Check 5: No duplicate state identifiers
    seen_states: set[str] = set()
    dup_states = []
    for s in wf.states:
        if s.unique_identifier in seen_states:
            dup_states.append(s.unique_identifier)
        seen_states.add(s.unique_identifier)
    checks.append(ValidationCheck(
        check="No duplicate state identifiers",
        passed=len(dup_states) == 0,
        details=f"Duplicates: {dup_states}" if dup_states else None,
    ))

    # Check 6: No duplicate transition identifiers
    seen_transitions: set[str] = set()
    dup_transitions = []
    for t in wf.transitions:
        if t.unique_identifier in seen_transitions:
            dup_transitions.append(t.unique_identifier)
        seen_transitions.add(t.unique_identifier)
    checks.append(ValidationCheck(
        check="No duplicate transition identifiers",
        passed=len(dup_transitions) == 0,
        details=f"Duplicates: {dup_transitions}" if dup_transitions else None,
    ))

    all_passed = all(c.passed for c in checks)
    return ValidationResult(valid=all_passed, checks=checks)


# ==============================================================================
# Runtime endpoints (Temporal operations)
# ==============================================================================


@app.post("/api/v1/workflows")
async def start_workflow(req: StartWorkflowRequest) -> dict:
    """Start a new Temporal workflow from a template and return its initial state."""
    client = _get_temporal_client()
    data = _read_template(req.template_id)

    try:
        WorkflowDefinition.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid template: {e}")

    sanitized_name = data.get("name", "unnamed").replace(" ", "-").lower()
    workflow_id = f"fsm-{sanitized_name}-{uuid.uuid4().hex[:8]}"

    await client.start_workflow(
        WORKFLOW_NAME,
        data,
        id=workflow_id,
        task_queue=config.temporal.task_queue,
    )

    handle = client.get_workflow_handle(workflow_id)
    state = await handle.query(QUERY_CURRENT_STATE)
    transitions = await handle.query(QUERY_AVAILABLE_TRANSITIONS)

    return {
        "workflow_id": workflow_id,
        "template_id": req.template_id,
        "current_state": state,
        "available_transitions": transitions,
    }


@app.get("/api/v1/workflows/{workflow_id}/state")
async def get_workflow_state(workflow_id: str) -> dict:
    """Query the current state of a running workflow."""
    client = _get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        state = await handle.query(QUERY_CURRENT_STATE)
    except Exception as e:
        logger.error("Failed to query state for workflow %s: %s", workflow_id, e)
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found or not running")
    return state


@app.get("/api/v1/workflows/{workflow_id}/transitions")
async def get_workflow_transitions(workflow_id: str) -> list[dict]:
    """Query available transitions from the current state of a workflow."""
    client = _get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        transitions = await handle.query(QUERY_AVAILABLE_TRANSITIONS)
    except Exception as e:
        logger.error("Failed to query transitions for workflow %s: %s", workflow_id, e)
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found or not running")
    return transitions


@app.post("/api/v1/workflows/{workflow_id}/transition")
async def trigger_transition(workflow_id: str, req: TransitionRequest) -> dict:
    """Send a transition signal to a workflow and return the updated state."""
    client = _get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)

    try:
        available = await handle.query(QUERY_AVAILABLE_TRANSITIONS)
    except Exception as e:
        logger.error("Failed to query transitions for workflow %s: %s", workflow_id, e)
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found or not running")

    valid_ids = [t["transition_id"] for t in available]
    if req.transition_id not in valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"'{req.transition_id}' is not valid. Available: {valid_ids}",
        )

    await handle.signal(SIGNAL_NAME, req.transition_id)

    return {"status": "signal_sent", "transition_id": req.transition_id}


@app.get("/api/v1/workflows/{workflow_id}/audit")
async def get_audit_trail(workflow_id: str) -> list[dict]:
    """Query the full audit trail of a workflow."""
    client = _get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        trail = await handle.query(QUERY_AUDIT_TRAIL)
    except Exception as e:
        logger.error("Failed to query audit trail for workflow %s: %s", workflow_id, e)
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found or not running")
    return trail


if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host=config.api_server.host,
        port=config.api_server.port,
        reload=True,
    )
