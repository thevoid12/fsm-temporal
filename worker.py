"""Temporal worker process for the FSM engine.
Connects to Temporal server and registers the FSM workflow and task callback activity.
"""

import asyncio
import logging

from temporalio import workflow
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from config import load_config

logger = logging.getLogger(__name__)

with workflow.unsafe.imports_passed_through():
    from activities import execute_task_callback
    from workflows import FSMWorkflow


async def main() -> None:
    """Start the FSM worker and listen for tasks."""
    config = load_config()

    client = await Client.connect(
        config.temporal.server_address,
        data_converter=pydantic_data_converter,
    )
    # note that you can add few more configuration options here.
    # workers can be scaled in 2 ways
    #     1. Vertical (per-worker concurrency)
    # Tune the max_concurrent_activities, max_concurrent_workflow_tasks, and thread pool size within a single worker process.
    # 2. Horizontal (more worker processes)
    # Run multiple worker processes polling the same task queue. Temporal server distributes tasks across all workers on that
    # queue.
    # python worker.py &
    # python worker.py &
    # python worker.py &
    # remember workers wont scale automatically by default out of the box by temporal Auto-scaling is not built-in but achievable via KEDA scaler
    # (Kubernetes) or resource-based tuning (per-worker).
    worker = Worker(
        client,
        task_queue=config.temporal.task_queue,
        workflows=[FSMWorkflow],
        activities=[execute_task_callback],
    )
    logger.info(
        "FSM Worker started",
        extra={"task_queue": config.temporal.task_queue, "server": config.temporal.server_address},
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
