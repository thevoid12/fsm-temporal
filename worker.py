"""Temporal worker process for the FSM engine.
Connects to Temporal server and registers the FSM workflow and task callback activity.
"""

import asyncio

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker

from config import load_config

with workflow.unsafe.imports_passed_through():
    from activities import execute_task_callback
    from workflows import FSMWorkflow


async def main() -> None:
    """Start the FSM worker and listen for tasks."""
    config = load_config()

    client = await Client.connect(config.temporal.server_address)
    worker = Worker(
        client,
        task_queue=config.temporal.task_queue,
        workflows=[FSMWorkflow],
        activities=[execute_task_callback],
    )
    workflow.logger.info(
        "FSM Worker started",
        extra={"task_queue": config.temporal.task_queue, "server": config.temporal.server_address},
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
