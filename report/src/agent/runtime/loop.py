"""
Corax Orchestrator - Execution Loop.

Provides the main autonomous execution loop for the agent runtime.
Manages continuous goal-driven execution with pause/resume/cancel
support, progress tracking, and error recovery.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Awaitable, Set
import asyncio
from uuid import uuid4

from src.core.logging import get_logger
from src.core.exceptions import CoraxError
from src.agent.runtime.lifecycle import (
    LifecycleManager,
    LifecycleState,
    LifecycleEvent,
)
from src.agent.runtime.scheduler import TaskScheduler, TaskPriority
from src.agent.execution.workflow import Workflow, WorkflowStep, WorkflowStatus
from src.agent.execution.context import ExecutionContext
from src.agent.modes.base import AgentMode, ActionProposal, ActionRisk

logger = get_logger(__name__)


@dataclass
class LoopMetrics:
    """Metrics collected during execution loop operation."""
    total_cycles: int = 0
    total_actions_executed: int = 0
    total_actions_approved: int = 0
    total_actions_denied: int = 0
    total_errors: int = 0
    total_recoveries: int = 0
    total_auto_approved: int = 0
    start_time: Optional[str] = None
    last_cycle_time: Optional[str] = None
    average_cycle_duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cycles": self.total_cycles,
            "total_actions_executed": self.total_actions_executed,
            "total_actions_approved": self.total_actions_approved,
            "total_actions_denied": self.total_actions_denied,
            "total_errors": self.total_errors,
            "total_recoveries": self.total_recoveries,
            "total_auto_approved": self.total_auto_approved,
            "start_time": self.start_time,
            "last_cycle_time": self.last_cycle_time,
            "average_cycle_duration": round(self.average_cycle_duration, 3),
        }


class ExecutionLoop:
    """
    Main autonomous execution loop for the agent runtime.

    The execution loop continuously processes goals by:
    1. Analyzing the current state and pending goals
    2. Planning the next actions
    3. Getting mode approval for actions
    4. Executing approved actions
    5. Handling results and errors
    6. Updating state and metrics

    Features:
    - Continuous goal-driven execution
    - Pause/resume/cancel support
    - Action approval via mode system
    - Automatic error recovery
    - Progress tracking and metrics
    - Configurable cycle timing
    """

    def __init__(
        self,
        lifecycle: LifecycleManager,
        scheduler: TaskScheduler,
        cycle_delay: float = 0.5,
        max_actions_per_cycle: int = 3,
    ) -> None:
        self.lifecycle = lifecycle
        self.scheduler = scheduler
        self.cycle_delay = cycle_delay
        self.max_actions_per_cycle = max_actions_per_cycle

        self._mode: Optional[AgentMode] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._paused: bool = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._metrics = LoopMetrics()
        self._progress_callbacks: List[Callable[..., Awaitable[None]]] = []
        self._action_executors: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._pending_goals: List[str] = []
        self._current_goal: Optional[str] = None
        self._current_workflow: Optional[Workflow] = None
        self._context: Optional[ExecutionContext] = None

    @property
    def mode(self) -> Optional[AgentMode]:
        """Get the current agent mode."""
        return self._mode

    @mode.setter
    def mode(self, mode: Optional[AgentMode]) -> None:
        """Set the current agent mode."""
        self._mode = mode

    @property
    def metrics(self) -> LoopMetrics:
        """Get the current loop metrics."""
        return self._metrics

    @property
    def is_running(self) -> bool:
        """Check if the loop is running."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """Check if the loop is paused."""
        return self._paused

    @property
    def current_goal(self) -> Optional[str]:
        """Get the current goal being executed."""
        return self._current_goal

    @property
    def current_workflow(self) -> Optional[Workflow]:
        """Get the current workflow being executed."""
        return self._current_workflow

    def register_action_executor(
        self,
        action_type: str,
        executor: Callable[..., Awaitable[Any]],
    ) -> None:
        """
        Register an executor for a specific action type.

        Args:
            action_type: The action type to handle
            executor: Async function that executes the action
        """
        self._action_executors[action_type] = executor
        logger.debug("Action executor registered", action_type=action_type)

    def on_progress(
        self, callback: Callable[..., Awaitable[None]]
    ) -> None:
        """Register a progress callback."""
        self._progress_callbacks.append(callback)

    def add_goal(self, goal: str) -> None:
        """
        Add a goal to the execution queue.

        Args:
            goal: The goal description
        """
        self._pending_goals.append(goal)
        logger.info("Goal added to queue", goal=goal, queue_size=len(self._pending_goals))

    def add_goals(self, goals: List[str]) -> None:
        """Add multiple goals to the execution queue."""
        self._pending_goals.extend(goals)
        logger.info("Goals added to queue", count=len(goals))

    def clear_goals(self) -> None:
        """Clear all pending goals."""
        self._pending_goals.clear()
        logger.info("Pending goals cleared")

    async def start(self) -> None:
        """Start the execution loop."""
        if self._running:
            return

        self._running = True
        self._paused = False
        self._pause_event.set()
        self._metrics.start_time = datetime.now(timezone.utc).isoformat()
        self._loop_task = asyncio.create_task(self._execution_loop())

        await self.lifecycle.transition(
            LifecycleEvent.START,
            reason="Execution loop started",
        )

        logger.info("Execution loop started")

    async def stop(self) -> None:
        """Stop the execution loop."""
        self._running = False
        self._pause_event.set()  # Unblock if paused

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        await self.lifecycle.transition(
            LifecycleEvent.TERMINATE,
            reason="Execution loop stopped",
        )

        logger.info("Execution loop stopped")

    async def pause(self) -> None:
        """Pause the execution loop."""
        if self._running and not self._paused:
            self._paused = True
            self._pause_event.clear()
            await self.lifecycle.transition(
                LifecycleEvent.PAUSE,
                reason="Execution loop paused by user",
            )
            logger.info("Execution loop paused")

    async def resume(self) -> None:
        """Resume the execution loop."""
        if self._paused:
            self._paused = False
            self._pause_event.set()
            await self.lifecycle.transition(
                LifecycleEvent.RESUME,
                reason="Execution loop resumed by user",
            )
            logger.info("Execution loop resumed")

    async def cancel(self) -> None:
        """Cancel the current execution."""
        if self._running:
            self._current_goal = None
            self._current_workflow = None
            self._pause_event.set()  # Unblock if paused
            await self.lifecycle.transition(
                LifecycleEvent.CANCEL,
                reason="Execution cancelled by user",
            )
            logger.info("Execution cancelled")

    def get_metrics(self) -> Dict[str, Any]:
        """Get execution loop metrics."""
        return self._metrics.to_dict()

    def get_status(self) -> Dict[str, Any]:
        """Get the current execution loop status."""
        return {
            "running": self._running,
            "paused": self._paused,
            "current_goal": self._current_goal,
            "pending_goals": len(self._pending_goals),
            "has_workflow": self._current_workflow is not None,
            "lifecycle_state": self.lifecycle.state_name,
            "metrics": self._metrics.to_dict(),
        }

    async def _execution_loop(self) -> None:
        """Main execution loop body."""
        while self._running:
            try:
                # Check pause state
                await self._pause_event.wait()

                if not self._running:
                    break

                cycle_start = datetime.now(timezone.utc)

                # Process one cycle
                await self._process_cycle()

                # Update metrics
                self._metrics.total_cycles += 1
                self._metrics.last_cycle_time = datetime.now(timezone.utc).isoformat()

                # Calculate average cycle duration
                cycle_duration = (
                    datetime.now(timezone.utc) - cycle_start
                ).total_seconds()
                if self._metrics.total_cycles == 1:
                    self._metrics.average_cycle_duration = cycle_duration
                else:
                    self._metrics.average_cycle_duration = (
                        self._metrics.average_cycle_duration * 0.9
                        + cycle_duration * 0.1
                    )

                # Notify progress
                await self._notify_progress()

                # Brief delay to prevent busy-waiting
                await asyncio.sleep(self.cycle_delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._metrics.total_errors += 1
                logger.error("Execution loop error", error=str(e))
                await self._handle_loop_error(e)
                await asyncio.sleep(1)

    async def _process_cycle(self) -> None:
        """Process one execution cycle."""
        # If we have a current workflow, continue executing it
        if self._current_workflow:
            await self._continue_workflow()
            return

        # If we have a current goal but no workflow, create one
        if self._current_goal:
            await self._start_goal_execution()
            return

        # Pick next goal from queue
        if self._pending_goals:
            self._current_goal = self._pending_goals.pop(0)
            logger.info("Processing next goal", goal=self._current_goal)
            return

        # Nothing to do - ensure lifecycle reflects idle state
        if self.lifecycle.is_running:
            await self.lifecycle.transition(
                LifecycleEvent.COMPLETE,
                reason="No pending goals",
            )

    async def _start_goal_execution(self) -> None:
        """Start executing the current goal."""
        if not self._current_goal:
            return

        # Transition to running state
        if not self.lifecycle.is_running:
            await self.lifecycle.transition(
                LifecycleEvent.EXECUTE,
                reason=f"Executing goal: {self._current_goal}",
            )

        # Create execution context
        self._context = ExecutionContext(
            workflow_id=str(uuid4()),
        )

        # Create a simple workflow for the goal
        self._current_workflow = Workflow(
            workflow_id=self._context.workflow_id,
            name=self._current_goal[:50],
            description=self._current_goal,
        )

        logger.info(
            "Starting goal execution",
            goal=self._current_goal,
            workflow_id=self._current_workflow.workflow_id,
        )

    async def _continue_workflow(self) -> None:
        """Continue executing the current workflow."""
        workflow = self._current_workflow
        if not workflow:
            return

        actions_this_cycle = 0

        while actions_this_cycle < self.max_actions_per_cycle:
            if workflow.is_complete() or workflow.has_failed():
                await self._finalize_workflow()
                return

            # Get next ready step
            step = workflow.get_next_pending_step()
            if not step:
                # Check for deadlock
                if workflow.get_pending_steps():
                    logger.warning(
                        "Workflow deadlock detected",
                        pending=[s.step_id for s in workflow.get_pending_steps()],
                    )
                    workflow.error = "Deadlock: pending steps have unmet dependencies"
                    workflow.status = WorkflowStatus.FAILED
                    await self._finalize_workflow()
                return

            # Execute the step
            await self._execute_step(workflow, step)
            actions_this_cycle += 1

    async def _execute_step(
        self, workflow: Workflow, step: WorkflowStep
    ) -> None:
        """Execute a single workflow step."""
        step.status = WorkflowStatus.RUNNING
        step.started_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Executing step",
            workflow=workflow.workflow_id,
            step=step.step_id,
            action=step.action_type,
        )

        try:
            # Request mode approval if needed
            if step.action_type and self._mode:
                approved = await self._request_approval(step)
                if not approved:
                    step.status = WorkflowStatus.SKIPPED
                    step.error = "Action not approved"
                    self._metrics.total_actions_denied += 1
                    return

            self._metrics.total_actions_approved += 1

            # Execute the action
            if step.timeout_seconds:
                result = await asyncio.wait_for(
                    self._execute_action(step),
                    timeout=step.timeout_seconds,
                )
            else:
                result = await self._execute_action(step)

            step.result = result
            step.status = WorkflowStatus.COMPLETED
            self._metrics.total_actions_executed += 1

            if self._context:
                self._context.store_step_result(step.step_id, result)

            logger.info(
                "Step completed",
                step=step.step_id,
                action=step.action_type,
            )

        except asyncio.TimeoutError:
            step.status = WorkflowStatus.FAILED
            step.error = f"Step timed out after {step.timeout_seconds}s"
            self._metrics.total_errors += 1
            logger.error("Step timed out", step=step.step_id)

        except Exception as e:
            step.status = WorkflowStatus.FAILED
            step.error = str(e)
            self._metrics.total_errors += 1
            logger.error("Step failed", step=step.step_id, error=str(e))

            # Handle retry
            if step.retry_count < step.max_retries:
                step.retry_count += 1
                step.status = WorkflowStatus.PENDING
                logger.info(
                    "Retrying step",
                    step=step.step_id,
                    attempt=step.retry_count,
                )

        finally:
            step.completed_at = datetime.now(timezone.utc).isoformat()

    async def _execute_action(self, step: WorkflowStep) -> Any:
        """Execute the action for a step."""
        if not step.action_type:
            return {"status": "no_action"}

        executor = self._action_executors.get(step.action_type)
        if executor:
            return await executor(
                step_id=step.step_id,
                parameters=step.parameters,
                context=self._context,
            )

        logger.warning(
            "No executor for action type",
            action_type=step.action_type,
        )
        return {
            "status": "not_implemented",
            "action_type": step.action_type,
        }

    async def _request_approval(self, step: WorkflowStep) -> bool:
        """Request approval for a step action from the current mode."""
        if not self._mode:
            return True

        risk = self._classify_step_risk(step)
        proposal = ActionProposal(
            action_id=step.step_id,
            action_type=step.action_type or "unknown",
            description=step.description or step.name,
            risk=risk,
            parameters=step.parameters,
            rationale=f"Workflow step: {step.name}",
            estimated_duration=step.timeout_seconds,
        )

        approved = await self._mode.evaluate_action(proposal)

        if proposal.auto_approved:
            self._metrics.total_auto_approved += 1

        return approved

    def _classify_step_risk(self, step: WorkflowStep) -> ActionRisk:
        """Classify the risk level of a step."""
        action_type = step.action_type or ""

        if any(kw in action_type for kw in ["install", "delete", "format", "admin"]):
            return ActionRisk.HIGH
        if any(kw in action_type for kw in ["download", "configure", "modify", "network"]):
            return ActionRisk.MEDIUM
        if any(kw in action_type for kw in ["scan", "check", "list", "get", "query"]):
            return ActionRisk.LOW

        return ActionRisk.SAFE

    async def _finalize_workflow(self) -> None:
        """Finalize the current workflow."""
        workflow = self._current_workflow
        if not workflow:
            return

        if workflow.has_failed():
            workflow.status = WorkflowStatus.FAILED
            await self.lifecycle.transition(
                LifecycleEvent.FAIL,
                reason=f"Workflow failed: {workflow.error}",
            )
            logger.error("Workflow failed", workflow=workflow.workflow_id)
        else:
            workflow.status = WorkflowStatus.COMPLETED
            await self.lifecycle.transition(
                LifecycleEvent.COMPLETE,
                reason="Workflow completed successfully",
            )
            logger.info(
                "Workflow completed",
                workflow=workflow.workflow_id,
                steps=len(workflow.get_completed_steps()),
            )

        workflow.completed_at = datetime.now(timezone.utc).isoformat()
        self._current_goal = None
        self._current_workflow = None
        self._context = None

    async def _handle_loop_error(self, error: Exception) -> None:
        """Handle an error in the execution loop."""
        self._metrics.total_errors += 1

        try:
            await self.lifecycle.transition(
                LifecycleEvent.ERROR,
                reason=f"Loop error: {str(error)}",
            )
        except ValueError:
            # If transition fails, force error state
            await self.lifecycle.force_transition(
                LifecycleState.ERROR,
                reason=f"Loop error: {str(error)}",
            )

        logger.error("Execution loop error", error=str(error))

    async def _notify_progress(self) -> None:
        """Notify progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                await callback(self.get_status())
            except Exception as e:
                logger.error("Progress callback error", error=str(e))
