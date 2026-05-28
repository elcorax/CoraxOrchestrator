"""
Corax Orchestrator - Runtime Engine.

The central orchestrator for the agent runtime system. Integrates
the lifecycle manager, execution loop, task scheduler, and recovery
system into a unified runtime environment.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio

from src.core.logging import get_logger
from src.core.exceptions import CoraxError
from src.agent.runtime.lifecycle import (
    LifecycleManager,
    LifecycleState,
    LifecycleEvent,
)
from src.agent.runtime.loop import ExecutionLoop, LoopMetrics
from src.agent.runtime.scheduler import TaskScheduler, TaskPriority, ScheduledTask
from src.agent.runtime.recovery import RuntimeRecovery, RecoveryPoint
from src.agent.modes.base import AgentMode, AgentModeType
from src.agent.modes.safe_mode import SafeMode
from src.agent.modes.assisted_mode import AssistedMode
from src.agent.modes.autonomous_mode import AutonomousMode
from src.agent.state import AgentState, AgentStatus

logger = get_logger(__name__)


@dataclass
class RuntimeConfig:
    """Configuration for the runtime engine."""
    max_concurrent_tasks: int = 5
    cycle_delay: float = 0.5
    max_actions_per_cycle: int = 3
    auto_save_interval: int = 30
    max_recovery_points: int = 10
    enable_recovery: bool = True
    default_mode: AgentModeType = AgentModeType.SAFE


class RuntimeEngine:
    """
    Central runtime engine that integrates all runtime subsystems.

    The RuntimeEngine provides:
    - Unified lifecycle management
    - Goal-driven execution loop
    - Task scheduling and prioritization
    - Crash recovery and restart support
    - Mode management (safe/assisted/autonomous)
    - Session management
    - Progress notifications
    - Comprehensive metrics

    Usage:
        engine = RuntimeEngine()
        await engine.initialize()
        await engine.start()
        engine.add_goal("Scan system and install tools")
        await engine.run_forever()
    """

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        agent_state: Optional[AgentState] = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.agent_state = agent_state or AgentState()

        # Initialize subsystems
        self.lifecycle = LifecycleManager()
        self.scheduler = TaskScheduler(
            max_concurrent=self.config.max_concurrent_tasks,
        )
        self.recovery = RuntimeRecovery(
            auto_save_interval=self.config.auto_save_interval,
            max_recovery_points=self.config.max_recovery_points,
        )
        self.loop = ExecutionLoop(
            lifecycle=self.lifecycle,
            scheduler=self.scheduler,
            cycle_delay=self.config.cycle_delay,
            max_actions_per_cycle=self.config.max_actions_per_cycle,
        )

        # Mode management
        self._mode_map: Dict[AgentModeType, AgentMode] = {}
        self._current_mode_type: AgentModeType = self.config.default_mode

        # Callbacks
        self._approval_callback: Optional[Callable] = None
        self._notification_callback: Optional[Callable] = None

        # State
        self._initialized: bool = False
        self._running: bool = False
        self._main_task: Optional[asyncio.Task] = None

    @property
    def mode(self) -> AgentMode:
        """Get the current agent mode."""
        return self._mode_map.get(
            self._current_mode_type,
            self._mode_map.get(AgentModeType.SAFE),
        )

    @property
    def mode_type(self) -> AgentModeType:
        """Get the current mode type."""
        return self._current_mode_type

    @property
    def is_initialized(self) -> bool:
        """Check if the engine is initialized."""
        return self._initialized

    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._running

    # --- Initialization ---

    async def initialize(self) -> None:
        """Initialize the runtime engine and all subsystems."""
        if self._initialized:
            return

        logger.info("Initializing runtime engine")

        # Initialize modes
        self._init_modes()

        # Initialize lifecycle
        await self.lifecycle.transition(
            LifecycleEvent.INIT,
            reason="Runtime engine initialization",
        )

        # Check for recovery
        if self.config.enable_recovery and self.recovery.has_recovery_point():
            await self._attempt_recovery()

        self._initialized = True
        logger.info("Runtime engine initialized")

    def _init_modes(self) -> None:
        """Initialize the three agent modes."""
        safe = SafeMode()
        assisted = AssistedMode()
        autonomous = AutonomousMode()

        # Configure callbacks
        if self._approval_callback:
            for mode in [safe, assisted, autonomous]:
                mode.set_approval_callback(self._approval_callback)
        if self._notification_callback:
            for mode in [safe, assisted, autonomous]:
                mode.set_notification_callback(self._notification_callback)

        self._mode_map = {
            AgentModeType.SAFE: safe,
            AgentModeType.ASSISTED: assisted,
            AgentModeType.AUTONOMOUS: autonomous,
        }

        # Link mode to execution loop
        self.loop.mode = self.mode

    async def _attempt_recovery(self) -> None:
        """Attempt to recover from a previous crash."""
        logger.info("Recovery points found, attempting recovery")

        point = await self.recovery.load_latest_recovery_point()
        if point:
            logger.info(
                "Loaded recovery point",
                point_id=point.point_id,
                state=point.lifecycle_state,
                session_id=point.session_id,
            )

            # Restore mode
            try:
                mode_type = AgentModeType(point.mode)
                self.set_mode(mode_type)
            except ValueError:
                logger.warning("Could not restore mode from recovery point")

            # Restore session if available
            if point.session_id:
                session = await self.agent_state.resume_session(point.session_id)
                if session:
                    logger.info("Session restored from recovery", session_id=point.session_id)

            await self.lifecycle.transition(
                LifecycleEvent.RECOVER,
                reason="Recovery from previous crash",
                metadata={
                    "recovery_point_id": point.point_id,
                    "previous_state": point.lifecycle_state,
                },
            )

    # --- Lifecycle Management ---

    async def start(self) -> None:
        """Start the runtime engine."""
        if not self._initialized:
            await self.initialize()

        if self._running:
            return

        self._running = True

        # Start subsystems
        await self.scheduler.start()
        await self.recovery.start_auto_save()
        await self.loop.start()

        logger.info("Runtime engine started")

    async def stop(self) -> None:
        """Stop the runtime engine gracefully."""
        if not self._running:
            return

        logger.info("Stopping runtime engine")

        # Stop subsystems in reverse order
        await self.loop.stop()
        await self.recovery.stop_auto_save()
        await self.scheduler.stop()

        # Save final recovery point
        await self._save_recovery_point()

        self._running = False

        await self.lifecycle.transition(
            LifecycleEvent.TERMINATE,
            reason="Runtime engine stopped",
        )

        logger.info("Runtime engine stopped")

    async def run_forever(self) -> None:
        """Run the engine until explicitly stopped."""
        if not self._running:
            await self.start()

        self._main_task = asyncio.create_task(self._run_forever_loop())

        try:
            await self._main_task
        except asyncio.CancelledError:
            pass

    async def _run_forever_loop(self) -> None:
        """Keep the engine running until stop is called."""
        while self._running:
            await asyncio.sleep(1)

    # --- Mode Management ---

    def set_mode(self, mode_type: AgentModeType) -> None:
        """
        Set the agent operation mode.

        Args:
            mode_type: The mode to switch to
        """
        mode = self._mode_map.get(mode_type)
        if not mode:
            raise CoraxError(
                message=f"Unknown mode: {mode_type.value}",
                recovery_hint=f"Available modes: {[m.value for m in self._mode_map]}",
            )

        self._current_mode_type = mode_type
        self.loop.mode = mode

        logger.info("Agent mode changed", mode=mode_type.value)

    def get_available_modes(self) -> List[Dict[str, Any]]:
        """Get information about all available modes."""
        return [
            {
                "type": mt.value,
                "description": self._get_mode_description(mt),
            }
            for mt in AgentModeType
        ]

    def _get_mode_description(self, mode_type: AgentModeType) -> str:
        """Get a description of a mode."""
        descriptions = {
            AgentModeType.SAFE: "All actions require explicit user approval. Maximum safety.",
            AgentModeType.ASSISTED: "Safe actions auto-approved, risky actions require approval.",
            AgentModeType.AUTONOMOUS: "Full autonomy within configured boundaries.",
        }
        return descriptions.get(mode_type, "")

    # --- Callback Configuration ---

    def on_approval_request(
        self, callback: Callable[..., Awaitable[bool]]
    ) -> None:
        """
        Set callback for user approval requests.

        Args:
            callback: Async function that receives ActionProposal
                      and returns True if approved
        """
        self._approval_callback = callback
        for mode in self._mode_map.values():
            mode.set_approval_callback(callback)

    def on_notification(
        self, callback: Callable[..., Awaitable[None]]
    ) -> None:
        """
        Set callback for user notifications.

        Args:
            callback: Async function that receives (event, data)
        """
        self._notification_callback = callback
        for mode in self._mode_map.values():
            mode.set_notification_callback(callback)

    def on_progress(
        self, callback: Callable[..., Awaitable[None]]
    ) -> None:
        """Register a workflow progress callback."""
        self.loop.on_progress(callback)

    # --- Goal Management ---

    def add_goal(self, goal: str) -> None:
        """
        Add a goal to the execution queue.

        Args:
            goal: The goal description
        """
        self.loop.add_goal(goal)

    def add_goals(self, goals: List[str]) -> None:
        """Add multiple goals to the execution queue."""
        self.loop.add_goals(goals)

    def clear_goals(self) -> None:
        """Clear all pending goals."""
        self.loop.clear_goals()

    def get_pending_goals(self) -> List[str]:
        """Get the list of pending goals."""
        return list(self.loop._pending_goals)

    # --- Task Scheduling ---

    async def schedule_task(
        self,
        name: str,
        executor_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        description: str = "",
        timeout_seconds: Optional[int] = None,
        max_retries: int = 0,
        depends_on: Optional[List[str]] = None,
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

        Returns:
            The created ScheduledTask
        """
        return await self.scheduler.schedule(
            name=name,
            executor_type=executor_type,
            parameters=parameters,
            priority=priority,
            description=description,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            depends_on=depends_on,
        )

    def register_task_executor(
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
        self.scheduler.register_executor(task_type, executor)

    def register_action_executor(
        self,
        action_type: str,
        executor: Callable[..., Awaitable[Any]],
    ) -> None:
        """
        Register an executor for a workflow action type.

        Args:
            action_type: The action type to handle
            executor: Async function that executes the action
        """
        self.loop.register_action_executor(action_type, executor)

    # --- Control ---

    async def pause(self) -> None:
        """Pause execution."""
        await self.loop.pause()

    async def resume(self) -> None:
        """Resume execution."""
        await self.loop.resume()

    async def cancel(self) -> None:
        """Cancel current execution."""
        await self.loop.cancel()

    # --- Status and Metrics ---

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive runtime status."""
        return {
            "initialized": self._initialized,
            "running": self._running,
            "lifecycle": self.lifecycle.to_dict(),
            "mode": self._current_mode_type.value,
            "loop": self.loop.get_status(),
            "scheduler": self.scheduler.to_dict(),
            "recovery": self.recovery.get_recovery_info(),
            "pending_goals": len(self.loop._pending_goals),
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get runtime metrics."""
        return {
            "loop": self.loop.get_metrics(),
            "scheduler": {
                "total_tasks": self.scheduler.get_task_count(),
                "queue_size": self.scheduler.get_queue_size(),
                "running": len(self.scheduler.get_running_tasks()),
                "completed": len(self.scheduler.get_completed_tasks()),
                "failed": len(self.scheduler.get_failed_tasks()),
            },
            "lifecycle": {
                "state": self.lifecycle.state_name,
                "total_transitions": self.lifecycle.get_transition_count(),
            },
        }

    # --- Recovery ---

    async def save_recovery_point(self) -> RecoveryPoint:
        """Manually save a recovery point."""
        return await self.recovery.save_recovery_point(
            lifecycle_state=self.lifecycle.state_name,
            mode=self._current_mode_type.value,
            metadata={
                "pending_goals": len(self.loop._pending_goals),
                "running_tasks": len(self.scheduler.get_running_tasks()),
            },
        )

    async def _save_recovery_point(self) -> None:
        """Internal: save a recovery point with current state."""
        await self.recovery.save_recovery_point(
            lifecycle_state=self.lifecycle.state_name,
            mode=self._current_mode_type.value,
        )

    # --- Session Management ---

    async def create_session(
        self,
        session_id: Optional[str] = None,
        mode: AgentModeType = AgentModeType.SAFE,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Create a new agent session.

        Args:
            session_id: Optional session ID
            mode: Initial agent mode
            configuration: Optional session configuration

        Returns:
            The created AgentSession
        """
        from uuid import uuid4
        session_id = session_id or f"session_{uuid4().hex[:8]}"
        session = await self.agent_state.create_session(
            session_id=session_id,
            mode=mode,
            configuration=configuration,
        )
        self.set_mode(mode)
        return session

    async def end_session(self) -> None:
        """End the current session."""
        await self.agent_state.update_status(AgentStatus.COMPLETED)
        await self.agent_state.flush()

    # --- Cleanup ---

    async def shutdown(self) -> None:
        """Complete shutdown of the runtime engine."""
        logger.info("Runtime engine shutting down")

        await self.stop()

        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass

        await self.agent_state.flush()

        logger.info("Runtime engine shutdown complete")
