"""Pydantic models for the FSM engine.
Defines the schema for workflow definitions, states, transitions,
task callback I/O, and structured logging contexts.
"""

from enum import StrEnum

from pydantic import BaseModel


# ==============================================================================
# Constants
# ==============================================================================

WORKFLOW_NAME = "FSMWorkflow"
SIGNAL_NAME = "transition"
QUERY_CURRENT_STATE = "current_state"
QUERY_AVAILABLE_TRANSITIONS = "available_transitions"
QUERY_AUDIT_TRAIL = "audit_trail"


# ==============================================================================
# Enums
# ==============================================================================


class HttpMethod(StrEnum):
    """Supported HTTP methods for task callbacks."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ConditionOperator(StrEnum):
    """Supported operators for conditional transition evaluation."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"


# ==============================================================================
# Workflow Definition Models (JSON schema)
# ==============================================================================


class TransitionCondition(BaseModel):
    """Condition evaluated against the task result body to determine auto-transition."""

    field: str
    operator: ConditionOperator
    value: str

    def evaluate(self, task_result_body: dict) -> bool:
        """Check if the condition matches against the task result."""
        actual = task_result_body.get(self.field)
        if actual is None:
            return False
        actual_str = str(actual)
        if self.operator == ConditionOperator.EQUALS:
            return actual_str == self.value
        if self.operator == ConditionOperator.NOT_EQUALS:
            return actual_str != self.value
        if self.operator == ConditionOperator.CONTAINS:
            return self.value in actual_str
        return False


class StateDefinition(BaseModel):
    """Defines a single state in the FSM, including optional task callback configuration."""

    unique_identifier: str
    display_label: str
    description: str = ""
    is_start: bool = False
    is_end: bool = False
    task_callback_url: str | None = None
    task_http_method: HttpMethod = HttpMethod.POST
    task_timeout_minutes: int = 5
    max_retries: int = 0
    retry_interval_seconds: int = 10


class TransitionDefinition(BaseModel):
    """Defines a valid transition between two states in the FSM."""

    unique_identifier: str
    display_label: str = ""
    source_state: str
    target_state: str
    auto_on_success: bool = False
    condition: TransitionCondition | None = None


class WorkflowDefinition(BaseModel):
    """Top-level FSM definition containing all states and transitions."""

    name: str
    description: str = ""
    states: list[StateDefinition]
    transitions: list[TransitionDefinition]

    def get_state(self, state_id: str) -> StateDefinition:
        """Look up a state by its unique identifier."""
        for state in self.states:
            if state.unique_identifier == state_id:
                return state
        raise KeyError(f"State '{state_id}' not found")

    def get_start_state(self) -> StateDefinition:
        """Return the state marked with is_start=True."""
        for state in self.states:
            if state.is_start:
                return state
        raise ValueError("No start state defined")

    def get_transitions_from(self, state_id: str) -> list[TransitionDefinition]:
        """Return all transitions originating from the given state."""
        return [t for t in self.transitions if t.source_state == state_id]

    def find_auto_transition(self, state_id: str, task_success: bool, task_result_body: dict) -> TransitionDefinition | None:
        """Find an auto-transition from the current state based on task result."""
        transitions = self.get_transitions_from(state_id)
        for t in transitions:
            if t.auto_on_success and task_success:
                return t
            if t.condition and t.condition.evaluate(task_result_body):
                return t
        return None

    def get_transition(self, transition_id: str) -> TransitionDefinition:
        """Look up a transition by its unique identifier."""
        for t in self.transitions:
            if t.unique_identifier == transition_id:
                return t
        raise KeyError(f"Transition '{transition_id}' not found")


# ==============================================================================
# Task Callback Models (Activity I/O)
# ==============================================================================


class TaskCallbackRequestBody(BaseModel):
    """JSON body sent to the task callback endpoint."""

    state_id: str
    workflow_id: str


class TaskCallbackHttpRequest(BaseModel):
    """Structured HTTP request kwargs for the task callback call."""

    json_body: dict | None = None
    query_params: dict | None = None

    def to_httpx_kwargs(self) -> dict:
        """Convert to httpx-compatible request kwargs, excluding None fields."""
        kwargs = {}
        if self.json_body is not None:
            kwargs["json"] = self.json_body
        if self.query_params is not None:
            kwargs["params"] = self.query_params
        return kwargs


class TaskCallbackInput(BaseModel):
    """Input payload sent to the HTTP callback activity."""

    callback_url: str
    http_method: HttpMethod
    state_id: str
    workflow_id: str


class TaskCallbackResult(BaseModel):
    """Result returned from the HTTP callback activity."""

    success: bool
    status_code: int
    body: str


# ==============================================================================
# Workflow Query/Response Models
# ==============================================================================


class AuditEntry(BaseModel):
    """Records a single state transition in the workflow history."""

    timestamp: str
    from_state: str | None
    to_state: str
    transition_id: str | None
    task_result: str | None = None


class FSMWorkflowResult(BaseModel):
    """Final output returned when the FSM workflow completes."""

    final_state: str
    audit_trail: list[AuditEntry]


class CurrentStateResponse(BaseModel):
    """Response for the current_state query."""

    state_id: str | None
    display_label: str | None


class AvailableTransitionResponse(BaseModel):
    """Single transition entry in the available_transitions query response."""

    transition_id: str
    display_label: str
    target_state: str


# ==============================================================================
# Structured Log Context Models
# ==============================================================================


class TaskCallbackLogContext(BaseModel):
    """Structured log context for task callback activity."""

    callback_url: str
    state_id: str
    workflow_id: str
    status_code: int | None = None
    error: str | None = None
    body: str | None = None


class StateEntryLogContext(BaseModel):
    """Structured log context when entering a state."""

    state_id: str
    display_label: str


class AutoTransitionLogContext(BaseModel):
    """Structured log context when an auto-transition fires."""

    transition_id: str
    target_state: str


class InvalidTransitionLogContext(BaseModel):
    """Structured log context when a transition is rejected as invalid."""

    transition_id: str
    current_state: str | None
    expected_source: str


# ==============================================================================
# API Server Models
# ==============================================================================


class TemplateSummary(BaseModel):
    """Summary of a workflow template for list views."""

    id: str
    name: str
    description: str


class ValidationCheck(BaseModel):
    """Result of a single structural validation check."""

    check: str
    passed: bool
    details: str | None = None


class ValidationResult(BaseModel):
    """Aggregated result of all validation checks on a template."""

    valid: bool
    checks: list[ValidationCheck]


class StartWorkflowRequest(BaseModel):
    """Request body for starting a new Temporal workflow from a template."""

    template_id: str


class TransitionRequest(BaseModel):
    """Request body for triggering a transition on a running workflow."""

    transition_id: str
