"""
Corax Orchestrator - Task Scheduler.

Provides task scheduling and prioritization for the agent runtime.
Manages concurrent task execution with priority-based ordering,
resource limits, and scheduling policies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Callable, Awaitable, Set
from uuid import uuid4
import asyncio
import heapq

from src.core.logging import get_logger

logger = get_logger(__name__)


class TaskPriority(Enum):
    """Priority levels for scheduled tasks."""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


class TaskStatus(Enum):
    """Status of a scheduled task."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"


@dataclass
class ScheduledTask:
    """
    A task scheduled for execution by the runtime.

    Tasks can be one-shot or recurring, with priority-based
    ordering and dependency management.
    """
    task_id: str
    name: str
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: int = 0
    retry_count: int = 0
    retry_delay_seconds: int = 5
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.name,
            "status": self.status.value,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "depends_on": self.depends_on,
            "error": self.error,
        }


class TaskScheduler:
    """
    Schedules and manages task execution for the agent runtime.

    Features:
    - Priority-based task ordering (heap queue)
    - Dependency resolution between tasks
    - Concurrent execution with configurable limits
    - Task timeout enforcement
    - Automatic retry on failure
    - Recurring task support
    - Task cancellation
    - Execution history tracking
    """

    def __init__(
        self,
        max_concurrent: int = 5,
    ) -> None:
        self.max_concurrent = max_concurrent
        self._task_queue: List[tuple] = []  # (priority, timestamp, task)
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._executor_map: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._lock = asyncio.Lock()
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running: bool = False

    def register_executor(
        self,
        task_type: str,
        executor: Callable[..., Awaitable[Any]],
    ) -> None:
        """
        Register an executor for a specific task type.

        Args:
            task_type: The type identifier for the task
            executor: Async function that executes the task
        """
        self._executor_map[task_type] = executor
        logger.debug("Task executor registered", task_type=task_type)

    async def schedule(
        self,
        name: str,
        executor_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        description: str = "",
        timeout_seconds: Optional[int] = None,
        max_retries: int = 0,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledTask:
        """
        Schedule a task for execution.

        Args:
            name: Human-readable task name
            executor_type: Type identifier matching a registered executor
            parameters: Parameters to pass to the executor
            priority: Task priority level
            description: Task description
            timeout_seconds: Maximum execution time
            max_retries: Number of retries on failure
            depends_on: List of task IDs that must complete first
            metadata: Additional task metadata

        Returns:
            The created ScheduledTask
        """
        task = ScheduledTask(
            task_id=str(uuid4()),
            name=name,
            description=description,
            priority=priority,
            depends_on=depends_on or [],
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            metadata={
                "executor_type": executor_type,
                "parameters": parameters or {},
                **(metadata or {}),
            },
        )

        async with self._lock:
            self._tasks[task.task_id] = task
            # Use priority value and timestamp for heap ordering
            heapq.heappush(
                self._task_queue,
                (priority.value, datetime.now(timezone.utc).isoformat(), task.task_id),
            )

        logger.info(
            "Task scheduled",
            task_id=task.task_id,
            name=name,
            priority=priority.name,
        )

        return task

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Task scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        # Cancel all running tasks
        for task_id, task in list(self._running_tasks.items()):
            task.cancel()
        logger.info("Task scheduler stopped")

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a scheduled or running task.

        Args:
            task_id: The task to cancel

        Returns:
            True if the task was cancelled
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                task.status = TaskStatus.CANCELLED
                logger.info("Task cancelled", task_id=task_id, name=task.name)
                return True

            if task.status == TaskStatus.RUNNING:
                running = self._running_tasks.get(task_id)
                if running:
                    running.cancel()
                    task.status = TaskStatus.CANCELLED
                    logger.info("Running task cancelled", task_id=task_id)
                    return True

            return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_tasks_by_status(self, status: TaskStatus) -> List[ScheduledTask]:
        """Get all tasks with a specific status."""
        return [
            t for t in self._tasks.values() if t.status == status
        ]

    def get_pending_tasks(self) -> List[ScheduledTask]:
        """Get all pending tasks."""
        return self.get_tasks_by_status(TaskStatus.PENDING)

    def get_running_tasks(self) -> List[ScheduledTask]:
        """Get all running tasks."""
        return self.get_tasks_by_status(TaskStatus.RUNNING)

    def get_completed_tasks(self) -> List[ScheduledTask]:
        """Get all completed tasks."""
        return self.get_tasks_by_status(TaskStatus.COMPLETED)

    def get_failed_tasks(self) -> List[ScheduledTask]:
        """Get all failed tasks."""
        return self.get_tasks_by_status(TaskStatus.FAILED)

    def get_task_count(self) -> int:
        """Get the total number of tasks."""
        return len(self._tasks)

    def get_queue_size(self) -> int:
        """Get the number of tasks waiting in the queue."""
        return len(self._task_queue)

    def clear_completed(self) -> int:
        """Remove all completed tasks from tracking."""
        completed_ids = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ]
        for tid in completed_ids:
            del self._tasks[tid]
        # Rebuild queue
        self._task_queue = [
            (p, ts, tid) for p, ts, tid in self._task_queue
            if tid in self._tasks
        ]
        heapq.heapify(self._task_queue)
        return len(completed_ids)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize scheduler state to dictionary."""
        return {
            "max_concurrent": self.max_concurrent,
            "running": self._running,
            "queue_size": self.get_queue_size(),
            "total_tasks": self.get_task_count(),
            "running_tasks": len(self._running_tasks),
            "pending": len(self.get_pending_tasks()),
            "completed": len(self.get_completed_tasks()),
            "failed": len(self.get_failed_tasks()),
        }

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that dispatches tasks."""
        while self._running:
            try:
                # Check if we can dispatch more tasks
                if len(self._running_tasks) < self.max_concurrent:
                    await self._dispatch_next_task()
                await asyncio.sleep(0.5)  # Poll interval
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error", error=str(e))
                await asyncio.sleep(1)

    async def _dispatch_next_task(self) -> None:
        """Dispatch the next ready task from the queue."""
        async with self._lock:
            # Find the highest priority ready task
            ready_tasks = []
            remaining = []

            while self._task_queue:
                priority, timestamp, task_id = heapq.heappop(self._task_queue)
                task = self._tasks.get(task_id)

                if not task or task.status == TaskStatus.CANCELLED:
                    continue

                if task.status != TaskStatus.PENDING:
                    remaining.append((priority, timestamp, task_id))
                    continue

                # Check dependencies
                deps_met = all(
                    dep_id in self._tasks
                    and self._tasks[dep_id].status == TaskStatus.COMPLETED
                    for dep_id in task.depends_on
                )

                if deps_met:
                    ready_tasks.append((priority, timestamp, task_id))
                    break  # Dispatch highest priority first
                else:
                    remaining.append((priority, timestamp, task_id))

            # Put remaining tasks back
            for item in remaining:
                heapq.heappush(self._task_queue, item)

            if not ready_tasks:
                return

            _, _, task_id = ready_tasks[0]
            task = self._tasks[task_id]
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc).isoformat()

        # Execute outside lock
        await self._execute_task(task)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a single task."""
        executor_type = task.metadata.get("executor_type", "")
        parameters = task.metadata.get("parameters", {})
        executor = self._executor_map.get(executor_type)

        if not executor:
            task.status = TaskStatus.FAILED
            task.error = f"No executor registered for type: {executor_type}"
            logger.error("Task execution failed", task_id=task.task_id, error=task.error)
            return

        logger.info(
            "Executing task",
            task_id=task.task_id,
            name=task.name,
            executor=executor_type,
        )

        try:
            if task.timeout_seconds:
                result = await asyncio.wait_for(
                    executor(**parameters),
                    timeout=task.timeout_seconds,
                )
            else:
                result = await executor(**parameters)

            task.status = TaskStatus.COMPLETED
            task.result = result if isinstance(result, dict) else {"result": result}
            task.completed_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                "Task completed",
                task_id=task.task_id,
                name=task.name,
            )

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task timed out after {task.timeout_seconds}s"
            logger.error("Task timed out", task_id=task.task_id)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error("Task failed", task_id=task.task_id, error=str(e))

        finally:
            # Remove from running tasks
            self._running_tasks.pop(task.task_id, None)

            # Handle retry
            if task.status == TaskStatus.FAILED and task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                logger.info(
                    "Rescheduling task for retry",
                    task_id=task.task_id,
                    attempt=task.retry_count,
                    max=task.max_retries,
                )
                # Re-queue with delay
                async with self._lock:
                    heapq.heappush(
                        self._task_queue,
                        (task.priority.value, datetime.now(timezone.utc).isoformat(), task.task_id),
                    )
