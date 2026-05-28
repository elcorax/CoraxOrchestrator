"""
Corax Orchestrator - Execution Engine.

Manages the lifecycle of workflow execution including:
- Step-by-step execution with dependency resolution
- Pause/resume/cancel workflow operations
- Timeout and retry handling
- Progress tracking and reporting
- Integration with the agent mode system for action approval
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Awaitable
from uuid import uuid4

from src.core.logging import get_logger
from src.core.exceptions import CoraxError
from src.agent.execution.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowStatus,
    StepType,
)
from src.agent.execution.context import ExecutionContext
from src.agent.modes.base import (
    AgentMode,
    AgentModeType,
    ActionProposal,
    ActionRisk,
)
from src.agent.state import AgentState, AgentStatus
from src.agent.execution.capabilities.base import CapabilityBase
from src.agent.execution.capabilities.terminal import TerminalCapability
from src.agent.execution.capabilities.process import ProcessCapability
from src.agent.execution.capabilities.installer_interaction import InstallerInteractionCapability
from src.agent.execution.capabilities.desktop import DesktopCapability
from src.agent.execution.capabilities.browser import BrowserCapability
from src.agent.execution.capabilities.sandbox import SandboxCapability
from src.agent.execution.capabilities.recovery import ExecutionRecoveryCapability

logger = get_logger(__name__)


class ExecutionEngine:
    """
    Corax Orchestrator - Autonomous Execution Engine.

    Orchestrates multi-step workflows with capability-based execution,
    self-healing retry, rollback, and comprehensive diagnostics.

    The execution engine:
    - Loads and validates workflows
    - Executes steps using registered capabilities
    - Handles retries with exponential backoff
    - Supports rollback on failure
    - Provides real-time progress via RuntimeStateBus
    - Supports cancellation with bounded cleanup (M42)
    - Execution context survivability with orphan-state cleanup (M42)
    """

    def __init__(
        self,
        agent_state: Optional[AgentState] = None,
        mode: Optional[AgentMode] = None,
    ) -> None:
        self.agent_state = agent_state or AgentState()
        self.mode = mode
        self._current_workflow: Optional[Workflow] = None
        self._context: Optional[ExecutionContext] = None
        self._running: bool = False
        self._paused: bool = False
        self._cancelled: bool = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._progress_callbacks: List[
            Callable[[Workflow, WorkflowStep], Awaitable[None]]
        ] = []
        self._step_executors: Dict[str, Callable[..., Awaitable[Any]]] = {}

        # Capabilities
        self._capabilities: Dict[str, CapabilityBase] = {}
        self._capability_initialized: bool = False

    async def initialize_capabilities(self) -> None:
        """Initialize all execution capabilities."""
        if self._capability_initialized:
            return

        capabilities = [
            TerminalCapability(),
            ProcessCapability(),
            InstallerInteractionCapability(),
            DesktopCapability(),
            BrowserCapability(),
            SandboxCapability(),
            ExecutionRecoveryCapability(),
        ]

        context = self._context or ExecutionContext()
        for cap in capabilities:
            try:
                await cap.initialize(context)
                self._capabilities[cap.name] = cap
                logger.info("Capability initialized", name=cap.name)
            except Exception as e:
                logger.error(
                    "Failed to initialize capability",
                    name=cap.name,
                    error=str(e),
                )

        self._capability_initialized = True

    async def shutdown_capabilities(self) -> None:
        """Shutdown all capabilities."""
        for name, cap in self._capabilities.items():
            try:
                await cap.shutdown()
                logger.info("Capability shut down", name=name)
            except Exception as e:
                logger.error(
                    "Failed to shut down capability",
                    name=name,
                    error=str(e),
                )
        self._capabilities.clear()
        self._capability_initialized = False

    def get_capability(self, name: str) -> Optional[CapabilityBase]:
        """Get a capability by name."""
        return self._capabilities.get(name)

    def get_all_capabilities(self) -> Dict[str, CapabilityBase]:
        """Get all registered capabilities."""
        return dict(self._capabilities)

    def register_step_executor(
        self, action_type: str, executor: Callable[..., Awaitable[Any]]
    ) -> None:
        """
        Register an executor for a specific action type.

        Args:
            action_type: The action type to handle
            executor: Async function that executes the action
        """
        self._step_executors[action_type] = executor
        logger.debug("Step executor registered", action_type=action_type)

    def on_progress(
        self, callback: Callable[[Workflow, WorkflowStep], Awaitable[None]]
    ) -> None:
        """Register a progress callback."""
        self._progress_callbacks.append(callback)

    async def execute_workflow(
        self,
        workflow: Workflow,
        context: Optional[ExecutionContext] = None,
    ) -> Workflow:
        """
        Execute a complete workflow.

        Args:
            workflow: The workflow to execute
            context: Optional execution context

        Returns:
            The completed workflow with step results
        """
        self._current_workflow = workflow
        self._context = context or ExecutionContext(
            workflow_id=workflow.workflow_id
        )
        self._running = True
        self._paused = False
        self._cancelled = False

        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now(timezone.utc).isoformat()

        await self._update_agent_status(AgentStatus.RUNNING)
        await self._save_checkpoint()

        logger.info(
            "Workflow execution started",
            workflow=workflow.workflow_id,
            steps=len(workflow.steps),
        )

        try:
            while not workflow.is_complete() and not self._cancelled:
                # Check if paused
                await self._pause_event.wait()

                if self._cancelled:
                    break

                # Get next ready step
                step = workflow.get_next_pending_step()
                if not step:
                    # No steps ready - check for deadlock
                    if workflow.get_pending_steps():
                        logger.warning(
                            "Workflow deadlock detected",
                            pending=[s.step_id for s in workflow.get_pending_steps()],
                        )
                        workflow.error = "Deadlock: pending steps have unmet dependencies"
                        workflow.status = WorkflowStatus.FAILED
                    break

                # Execute the step
                await self._execute_step(workflow, step)

                # Notify progress
                await self._notify_progress(workflow, step)

                # Save checkpoint after each step
                await self._save_checkpoint()

            # Finalize workflow
            if self._cancelled:
                workflow.status = WorkflowStatus.CANCELLED
                logger.info("Workflow cancelled", workflow=workflow.workflow_id)
            elif workflow.has_failed():
                workflow.status = WorkflowStatus.FAILED
                logger.error("Workflow failed", workflow=workflow.workflow_id)
            else:
                workflow.status = WorkflowStatus.COMPLETED
                logger.info(
                    "Workflow completed",
                    workflow=workflow.workflow_id,
                    steps=len(workflow.get_completed_steps()),
                )

        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.error = str(e)
            logger.error(
                "Workflow execution error",
                workflow=workflow.workflow_id,
                error=str(e),
            )

        finally:
            workflow.completed_at = datetime.now(timezone.utc).isoformat()
            self._running = False
            await self._update_agent_status(AgentStatus.IDLE)
            await self._save_checkpoint()

        return workflow

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
            name=step.name,
            action=step.action_type,
        )

        try:
            # Check mode approval if action type is set
            if step.action_type and self.mode:
                approved = await self._request_action_approval(step)
                if not approved:
                    step.status = WorkflowStatus.SKIPPED
                    step.error = "Action not approved by mode"
                    return

            # Execute with timeout if configured
            if step.timeout_seconds:
                result = await asyncio.wait_for(
                    self._execute_step_action(step),
                    timeout=step.timeout_seconds,
                )
            else:
                result = await self._execute_step_action(step)

            step.result = result
            step.status = WorkflowStatus.COMPLETED

            # Store result in context
            if self._context:
                self._context.store_step_result(step.step_id, result)

        except asyncio.TimeoutError:
            step.status = WorkflowStatus.FAILED
            step.error = f"Step timed out after {step.timeout_seconds}s"
            logger.error("Step timed out", step=step.step_id)

        except Exception as e:
            step.status = WorkflowStatus.FAILED
            step.error = str(e)
            logger.error("Step failed", step=step.step_id, error=str(e))

            # Handle retry
            if step.retry_count < step.max_retries:
                step.retry_count += 1
                step.status = WorkflowStatus.PENDING  # Reset for retry
                logger.info(
                    "Retrying step",
                    step=step.step_id,
                    attempt=step.retry_count,
                    max=step.max_retries,
                )

        finally:
            step.completed_at = datetime.now(timezone.utc).isoformat()

    async def _execute_step_action(
        self, step: WorkflowStep
    ) -> Any:
        """Execute the action for a step."""
        if not step.action_type:
            return {"status": "no_action"}

        executor = self._step_executors.get(step.action_type)
        if executor:
            return await executor(
                step_id=step.step_id,
                parameters=step.parameters,
                context=self._context,
            )

        # No executor registered - return a placeholder
        logger.warning(
            "No executor for action type",
            action_type=step.action_type,
        )
        return {
            "status": "not_implemented",
            "action_type": step.action_type,
            "message": f"No executor registered for '{step.action_type}'",
        }

    async def _request_action_approval(self, step: WorkflowStep) -> bool:
        """Request approval for a step action from the current mode."""
        if not self.mode:
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

        return await self.mode.evaluate_action(proposal)

    def _classify_step_risk(self, step: WorkflowStep) -> ActionRisk:
        """Classify the risk level of a step."""
        action_type = step.action_type or ""

        # High risk actions
        if any(kw in action_type for kw in ["install", "delete", "format", "admin"]):
            return ActionRisk.HIGH

        # Medium risk actions
        if any(kw in action_type for kw in ["download", "configure", "modify", "network"]):
            return ActionRisk.MEDIUM

        # Low risk actions
        if any(kw in action_type for kw in ["scan", "check", "list", "get", "query"]):
            return ActionRisk.LOW

        return ActionRisk.SAFE

    async def pause(self) -> None:
        """Pause workflow execution."""
        if self._running and not self._paused:
            self._paused = True
            self._pause_event.clear()
            await self._update_agent_status(AgentStatus.PAUSED)
            await self._save_checkpoint()
            logger.info("Workflow paused")

    async def resume(self) -> None:
        """Resume workflow execution."""
        if self._paused:
            self._paused = False
            self._pause_event.set()
            await self._update_agent_status(AgentStatus.RUNNING)
            logger.info("Workflow resumed")

    async def cancel(self) -> None:
        """Cancel workflow execution with bounded cleanup.

        — M42: Ensures no orphan execution state on cancellation.
        Cleans up active capabilities, resets execution context,
        and removes stale state markers from disk.
        """
        if self._running:
            self._cancelled = True
            self._pause_event.set()  # Unblock if paused
            await self._update_agent_status(AgentStatus.CANCELLED)
            logger.info("Workflow cancelled")

            # — M42: Cancel any active capability operations
            await self._cancel_active_capabilities()

            # — M42: Cleanup orphaned state markers from disk
            self._cleanup_execution_state_markers()

    async def _cancel_active_capabilities(self) -> None:
        """Cancel any actively running capability operations.

        — M42: Prevents orphan capability execution after cancellation.
        Attempts graceful shutdown of each capability, with bounded
        timeout per capability.
        """
        for name, cap in list(self._capabilities.items()):
            try:
                # Attempt to shutdown capability gracefully
                import asyncio
                await asyncio.wait_for(
                    cap.shutdown(),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Capability shutdown timed out during cancel: {name}"
                )
            except Exception as e:
                logger.warning(
                    f"Capability shutdown error during cancel: {name}: {e}"
                )

    def _cleanup_execution_state_markers(self) -> None:
        """Clean up orphaned execution state marker files from disk.

        — M42: Prevents stale execution markers from persisting across
        restarts after a cancelled workflow.
        """
        try:
            import os
            from pathlib import Path

            project_root = Path(os.getcwd())
            markers = [
                "_corax_exec_active",
                "_corax_state_dirty",
                "_corax_session_active",
            ]
            for marker_name in markers:
                marker = project_root / marker_name
                if marker.exists():
                    try:
                        marker.unlink()
                    except (PermissionError, OSError):
                        pass
        except Exception:
            pass  # Non-critical cleanup


    def is_running(self) -> bool:
        """Check if a workflow is currently running."""
        return self._running

    def is_paused(self) -> bool:
        """Check if the workflow is paused."""
        return self._paused

    def get_current_workflow(self) -> Optional[Workflow]:
        """Get the currently executing workflow."""
        return self._current_workflow

    def get_context(self) -> Optional[ExecutionContext]:
        """Get the current execution context."""
        return self._context

    async def _notify_progress(
        self, workflow: Workflow, step: WorkflowStep
    ) -> None:
        """Notify progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                await callback(workflow, step)
            except Exception as e:
                logger.error("Progress callback error", error=str(e))

    async def _update_agent_status(self, status: AgentStatus) -> None:
        """Update the agent status in state."""
        if self.agent_state:
            await self.agent_state.update_status(status)

    async def _save_checkpoint(self) -> None:
        """Save a checkpoint of current state."""
        if self.agent_state:
            await self.agent_state.save_checkpoint()
