"""CLI entrypoint for the FSM engine.
Supports starting workflows, sending transition signals, and querying workflow state.
"""

import asyncio
import json
import sys
import uuid

from temporalio.client import Client

from config import load_config
from models import (
    QUERY_AUDIT_TRAIL,
    QUERY_AVAILABLE_TRANSITIONS,
    QUERY_CURRENT_STATE,
    SIGNAL_NAME,
    WORKFLOW_NAME,
)


async def start_workflow(client: Client, task_queue: str, json_path: str) -> str:
    """Start a new FSM workflow from a JSON definition file."""
    with open(json_path) as f:
        workflow_def = json.load(f)

    workflow_id = f"fsm-{workflow_def.get('name', 'unnamed')}-{uuid.uuid4().hex[:8]}"
    handle = await client.start_workflow(
        WORKFLOW_NAME,
        workflow_def,
        id=workflow_id,
        task_queue=task_queue,
    )
    print(f"Started workflow: {handle.id}")
    return handle.id


async def send_transition(client: Client, workflow_id: str, transition_id: str) -> None:
    """Send a transition signal to a running workflow."""
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(SIGNAL_NAME, transition_id)
    print(f"Sent transition: {transition_id}")


async def query_current_state(client: Client, workflow_id: str) -> None:
    """Query and print the current state of a workflow."""
    handle = client.get_workflow_handle(workflow_id)
    state = await handle.query(QUERY_CURRENT_STATE)
    print(json.dumps(state, indent=2))


async def query_available_transitions(client: Client, workflow_id: str) -> None:
    """Query and print the available transitions from the current state."""
    handle = client.get_workflow_handle(workflow_id)
    transitions = await handle.query(QUERY_AVAILABLE_TRANSITIONS)
    print(json.dumps(transitions, indent=2))


async def query_audit_trail(client: Client, workflow_id: str) -> None:
    """Query and print the full audit trail of a workflow."""
    handle = client.get_workflow_handle(workflow_id)
    trail = await handle.query(QUERY_AUDIT_TRAIL)
    print(json.dumps(trail, indent=2))


def print_usage() -> None:
    """Print CLI usage instructions."""
    print("Usage:")
    print("  python main.py start [json_path]")
    print("  python main.py transition <workflow_id> <transition_id>")
    print("  python main.py state <workflow_id>")
    print("  python main.py transitions <workflow_id>")
    print("  python main.py audit <workflow_id>")


async def run() -> None:
    """Parse CLI args and dispatch to the appropriate command."""
    config = load_config()
    client = await Client.connect(config.temporal.server_address)

    command = sys.argv[1] if len(sys.argv) > 1 else "help"

    if command == "start":
        json_path = sys.argv[2] if len(sys.argv) > 2 else "workflow_definitions/e2e_test.json"
        await start_workflow(client, config.temporal.task_queue, json_path)
    elif command == "transition":
        await send_transition(client, sys.argv[2], sys.argv[3])
    elif command == "state":
        await query_current_state(client, sys.argv[2])
    elif command == "transitions":
        await query_available_transitions(client, sys.argv[2])
    elif command == "audit":
        await query_audit_trail(client, sys.argv[2])
    else:
        print_usage()


if __name__ == "__main__":
    asyncio.run(run())
