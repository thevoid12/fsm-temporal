"""Temporal workflow implementing a JSON-driven finite state machine.
Manages state transitions, task callback execution, conditional auto-transitions,
and exposes queries for current state, available transitions, and audit trail.
"""

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import execute_task_callback
    from models import (
        AuditEntry,
        AutoTransitionLogContext,
        AvailableTransitionResponse,
        CurrentStateResponse,
        FSMWorkflowResult,
        InvalidTransitionLogContext,
        StateEntryLogContext,
        TaskCallbackInput,
        TaskCallbackResult,
        WorkflowDefinition,
    )


@workflow.defn
class FSMWorkflow:
    """Generic FSM workflow driven by a WorkflowDefinition."""

    def __init__(self) -> None:
        self._current_state_id: str | None = None
        self._definition: WorkflowDefinition | None = None
        self._audit_trail: list[AuditEntry] = []
        self._transition_queue: list[str] = []
        self._completed: bool = False

    @workflow.run
    async def run(self, workflow_def_dict: dict) -> dict:
        """Run is the main entry point. Execute the FSM from start state to end state."""
        self._definition = WorkflowDefinition.model_validate(workflow_def_dict)

        start_state = self._definition.get_start_state()
        await self._enter_state(start_state.unique_identifier, transition_id=None)

        while not self._completed:
            await workflow.wait_condition(lambda: len(self._transition_queue) > 0)

            transition_id = self._transition_queue.pop(0)
            transition = self._definition.get_transition(transition_id)

            if transition.source_state != self._current_state_id:
                log_ctx = InvalidTransitionLogContext(
                    transition_id=transition_id,
                    current_state=self._current_state_id,
                    expected_source=transition.source_state,
                )
                workflow.logger.warning(
                    "Ignoring invalid transition",
                    extra=log_ctx.model_dump(),
                )
                continue

            await self._enter_state(transition.target_state, transition_id=transition_id)

        result = FSMWorkflowResult(
            final_state=self._current_state_id,
            audit_trail=self._audit_trail,
        )
        return result.model_dump()

    
    async def _enter_state(self, state_id: str, transition_id: str | None) -> None:
        """Enter a state, execute its task callback if defined, and check for auto-transitions."""
        previous_state = self._current_state_id
        self._current_state_id = state_id
        state_def = self._definition.get_state(state_id)

        log_ctx = StateEntryLogContext(
            state_id=state_id,
            display_label=state_def.display_label,
        )
        # using inbuilt temporol logging. this gives a lot of advantages
        workflow.logger.info("Entering state", extra=log_ctx.model_dump()) 

        task_result: TaskCallbackResult | None = None

        if state_def.task_callback_url:
            activity_input = TaskCallbackInput(
                callback_url=state_def.task_callback_url,
                http_method=state_def.task_http_method,
                state_id=state_id,
                workflow_id=workflow.info().workflow_id,
            )
            
            task_result = await workflow.execute_activity(
                execute_task_callback,
                activity_input,
                schedule_to_close_timeout=timedelta(minutes=state_def.task_timeout_minutes),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=state_def.retry_interval_seconds),
                    maximum_attempts=state_def.max_retries + 1,
                    backoff_coefficient=2.0, # exponential backoff
                ),
            )

        audit_entry = AuditEntry(
            timestamp=workflow.now().isoformat(), # deterministic, replay-safe timestamp
            from_state=previous_state,
            to_state=state_id,
            transition_id=transition_id,
            task_result=task_result.body if task_result else None,
        )
        self._audit_trail.append(audit_entry)

        if state_def.is_end:
            self._completed = True
            return

        if task_result:
            try:
                task_body = json.loads(task_result.body)
            except (json.JSONDecodeError, TypeError):
                task_body = {}

            auto_transition = self._definition.find_auto_transition(
                state_id, task_result.success, task_body
            )
            if auto_transition: #Doubt
                auto_log = AutoTransitionLogContext(
                    transition_id=auto_transition.unique_identifier,
                    target_state=auto_transition.target_state,
                )
                workflow.logger.info("Auto-transitioning", extra=auto_log.model_dump())
                await self._enter_state(
                    auto_transition.target_state,
                    transition_id=auto_transition.unique_identifier,
                )

    @workflow.signal
    async def transition(self, transition_id: str) -> None:
        """Receive a transition signal and queue it for processing."""
        try:
            self._definition.get_transition(transition_id)
        except KeyError:
            workflow.logger.warning(
                "Unknown transition signal received",
                extra={"transition_id": transition_id},
            )
            return
        self._transition_queue.append(transition_id)

    @workflow.query
    def current_state(self) -> dict:
        """Return the current state identifier and display label."""
        if not self._definition or not self._current_state_id:
            response = CurrentStateResponse(state_id=None, display_label=None)
            return response.model_dump()
        state = self._definition.get_state(self._current_state_id)
        response = CurrentStateResponse(
            state_id=state.unique_identifier,
            display_label=state.display_label,
        )
        return response.model_dump()

    @workflow.query
    def available_transitions(self) -> list[dict]:
        """Return all valid transitions from the current state."""
        if not self._definition or not self._current_state_id:
            return []
        transitions = self._definition.get_transitions_from(self._current_state_id)
        return [
            AvailableTransitionResponse(
                transition_id=t.unique_identifier,
                display_label=t.display_label,
                target_state=t.target_state,
            ).model_dump()
            for t in transitions
        ]

    @workflow.query
    def audit_trail(self) -> list[dict]:
        """Return the full history of state transitions."""
        return [entry.model_dump() for entry in self._audit_trail]
