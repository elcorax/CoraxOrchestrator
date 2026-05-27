"""
Corax Orchestrator - Agent Runtime.

The main orchestrator for the autonomous agent system. Manages the
complete lifecycle of autonomous execution including mode management,
workflow execution, reasoning, and state persistence.

Architecture:
    AgentRuntime
    ├── AgentState (persistence & checkpoints)
    ├── ExecutionEngine (workflow execution)
    ├── ReasoningEngine (planning & decisions)
    ├── ToolExecutor (tool invocation)
    └── AgentMode (safe/assisted/autonomous)
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Awaitable
from uuid import uuid4

from src.core.logging import get_logger
from src.core.exceptions import CoraxError
from src.agent.state import AgentState, AgentStatus, AgentSession
from src.agent.modes.base import (
    AgentMode,
    AgentModeType,
    ActionProposal,
    ActionRisk,
)
from src.agent.modes.safe_mode import SafeMode
from src.agent.modes.assisted_mode import AssistedMode
from src.agent.modes.autonomous_mode import AutonomousMode
from src.agent.execution.engine import ExecutionEngine
from src.agent.execution.workflow import Workflow, WorkflowStep, WorkflowStatus, StepType
from src.agent.execution.context import ExecutionContext
from src.agent.reasoning.engine import ReasoningEngine, ReasoningResult
from src.agent.reasoning.planner import Planner, Plan, PlanStep
from src.agent.reasoning.decisions import DecisionEngine, Decision
from src.agent.tool_executor import ToolExecutor

logger = get_logger(__name__)


class AgentRuntime:
    """
    Main runtime for the autonomous agent system.

    Provides:
    - Session management (create/resume/archive)
    - Mode management (safe/assisted/autonomous)
    - Workflow execution with pause/resume/cancel
    - Reasoning and planning
    - Tool execution
    - State persistence and checkpoints
    - Progress notifications
    """

    def __init__(
        self,
        agent_state: Optional[AgentState] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        reasoning_engine: Optional[ReasoningEngine] = None,
        tool_executor: Optional[ToolExecutor] = None,
        mode: Optional[AgentMode] = None,
    ) -> None:
        self.state = agent_state or AgentState()
        self.execution = execution_engine or ExecutionEngine(
            agent_state=self.state,
        )
        self.reasoning = reasoning_engine or ReasoningEngine()
        self.tools = tool_executor or ToolExecutor()
        self._mode: Optional[AgentMode] = mode
        self._mode_map: Dict[AgentModeType, AgentMode] = {}
        self._approval_callback: Optional[
            Callable[[ActionProposal], Awaitable[bool]]
        ] = None
        self._notification_callback: Optional[
            Callable[[str, Dict[str, Any]], Awaitable[None]]
        ] = None
        self._progress_callbacks: List[
            Callable[[Workflow, WorkflowStep], Awaitable[None]]
        ] = []
        self._running: bool = False
        self._auto_save_task: Optional[asyncio.Task] = None

        # Initialize default modes
        self._init_default_modes()

    def _init_default_modes(self) -> None:
        """Initialize the three default agent modes."""
        safe = SafeMode()
        assisted = AssistedMode()
        autonomous = AutonomousMode()

        self._mode_map = {
            AgentModeType.SAFE: safe,
            AgentModeType.ASSISTED: assisted,
            AgentModeType.AUTONOMOUS: autonomous,
        }

        # Set default mode to safe
        if not self._mode:
            self._mode = safe

    # --- Mode Management ---

    @property
    def mode(self) -> AgentMode:
        """Get the current agent mode."""
        return self._mode or self._mode_map[AgentModeType.SAFE]

    @property
    def mode_type(self) -> AgentModeType:
        """Get the current mode type."""
        return self.mode.mode_type

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

        # Configure callbacks
        if self._approval_callback:
            mode.set_approval_callback(self._approval_callback)
        if self._notification_callback:
            mode.set_notification_callback(self._notification_callback)

        self._mode = mode
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
            AgentModeType.SAFE: (
                "All actions require explicit user approval. "
                "Maximum safety, no autonomous execution."
            ),
            AgentModeType.ASSISTED: (
                "Safe actions auto-approved, risky actions require "
                "approval. Balance of automation and safety."
            ),
            AgentModeType.AUTONOMOUS: (
                "Full autonomy within configured boundaries. "
                "Actions auto-approved unless they exceed risk thresholds."
            ),
        }
        return descriptions.get(mode_type, "")

    # --- Callback Configuration ---

    def on_approval_request(
        self, callback: Callable[[ActionProposal], Awaitable[bool]]
    ) -> None:
        """
        Set callback for user approval requests.

        Args:
            callback: Async function that receives ActionProposal
                      and returns True if approved
        """
        self._approval_callback = callback
        # Update all modes
        for mode in self._mode_map.values():
            mode.set_approval_callback(callback)

    def on_notification(
        self, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """
        Set callback for user notifications.

        Args:
            callback: Async function that receives (event, data)
        """
        self._notification_callback = callback
        # Update all modes
        for mode in self._mode_map.values():
            mode.set_notification_callback(callback)

    def on_progress(
        self, callback: Callable[[Workflow, WorkflowStep], Awaitable[None]]
    ) -> None:
        """
        Register a workflow progress callback.

        Args:
            callback: Called after each step execution
        """
        self._progress_callbacks.append(callback)
        self.execution.on_progress(callback)

    # --- Session Management ---

    async def start_session(
        self,
        session_id: Optional[str] = None,
        mode: AgentModeType = AgentModeType.SAFE,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> AgentSession:
        """
        Start a new agent session.

        Args:
            session_id: Optional session ID (auto-generated if not provided)
            mode: Initial agent mode
            configuration: Optional session configuration

        Returns:
            The created AgentSession
        """
        session_id = session_id or f"session_{uuid4().hex[:8]}"
        session = await self.state.create_session(
            session_id=session_id,
            mode=mode,
            configuration=configuration,
        )

        self.set_mode(mode)
        self._running = True

        # Start auto-save task
        self._auto_save_task = asyncio.create_task(self._auto_save_loop())

        logger.info(
            "Agent session started",
            session_id=session_id,
            mode=mode.value,
        )

        return session

    async def resume_session(self, session_id: str) -> Optional[AgentSession]:
        """
        Resume a previously persisted session.

        Args:
            session_id: Session to resume

        Returns:
            AgentSession if found
        """
        session = await self.state.resume_session(session_id)
        if session:
            self.set_mode(session.mode)
            self._running = True
            self._auto_save_task = asyncio.create_task(self._auto_save_loop())
            logger.info("Agent session resumed", session_id=session_id)
        return session

    async def end_session(self) -> None:
        """End the current session and persist state."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass

        await self.state.update_status(AgentStatus.COMPLETED)
        await self.state.flush()
        self._running = False
        logger.info("Agent session ended")

    async def list_sessions(self) -> List[str]:
        """List all available sessions."""
        return await self.state.list_sessions()

    # --- Workflow Execution ---

    async def execute_goal(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """
        Execute a goal by planning and running a workflow.

        Args:
            goal: The goal to achieve
            context: Optional context for planning

        Returns:
            Completed Workflow
        """
        # Analyze the goal
        analysis = await self.reasoning.analyze_problem(
            goal=goal,
            context=context or {},
        )

        logger.info(
            "Goal analysis complete",
            goal=goal,
            confidence=analysis.confidence,
        )

        # Create a plan
        plan = await self.reasoning.create_plan(
            goal=goal,
            context=context or {},
            available_tools=self.tools.list_tools(),
        )

        # Convert plan to workflow
        workflow = self._plan_to_workflow(plan)

        # Execute the workflow
        return await self.execute_workflow(workflow)

    async def execute_workflow(
        self,
        workflow: Workflow,
        context: Optional[ExecutionContext] = None,
    ) -> Workflow:
        """
        Execute a workflow.

        Args:
            workflow: The workflow to execute
            context: Optional execution context

        Returns:
            Completed Workflow
        """
        # Link execution engine to current mode
        self.execution.mode = self.mode

        # Execute
        result = await self.execution.execute_workflow(
            workflow=workflow,
            context=context,
        )

        # Record execution in session
        await self.state.record_execution({
            "event": "workflow_completed",
            "workflow_id": workflow.workflow_id,
            "status": workflow.status.value,
            "steps_completed": len(workflow.get_completed_steps()),
            "progress": workflow.progress_percentage(),
        })

        return result

    async def pause_workflow(self) -> None:
        """Pause the currently executing workflow."""
        await self.execution.pause()

    async def resume_workflow(self) -> None:
        """Resume a paused workflow."""
        await self.execution.resume()

    async def cancel_workflow(self) -> None:
        """Cancel the currently executing workflow."""
        await self.execution.cancel()

    def is_workflow_running(self) -> bool:
        """Check if a workflow is currently running."""
        return self.execution.is_running()

    def is_workflow_paused(self) -> bool:
        """Check if the workflow is paused."""
        return self.execution.is_paused()

    def get_current_workflow(self) -> Optional[Workflow]:
        """Get the currently executing workflow."""
        return self.execution.get_current_workflow()

    # --- Reasoning ---

    async def analyze(self, goal: str, context: Dict[str, Any]) -> ReasoningResult:
        """Analyze a problem and determine approach."""
        return await self.reasoning.analyze_problem(goal=goal, context=context)

    async def plan(
        self,
        goal: str,
        context: Dict[str, Any],
        available_tools: Optional[List[str]] = None,
    ) -> Plan:
        """Create a plan to achieve a goal."""
        return await self.reasoning.create_plan(
            goal=goal,
            context=context,
            available_tools=available_tools,
        )

    async def decide(
        self,
        question: str,
        options: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Make a decision."""
        return await self.reasoning.make_decision(
            question=question,
            options=options,
            context=context,
        )

    async def assess_risk(
        self, action: str, context: Dict[str, Any]
    ) -> ReasoningResult:
        """Assess the risk of an action."""
        return await self.reasoning.assess_risk(action=action, context=context)

    # --- Tool Execution ---

    def register_tool(
        self,
        name: str,
        executor: Callable[..., Awaitable[Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool for execution."""
        self.tools.register_tool(name=name, executor=executor, metadata=metadata)

        # Also register with execution engine
        self.execution.register_step_executor(name, executor)

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute a tool."""
        return await self.tools.execute(
            tool_name=tool_name,
            parameters=parameters,
            timeout=timeout,
        )

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools."""
        return self.tools.list_tools()

    # --- State Management ---

    async def save_checkpoint(self) -> None:
        """Save a checkpoint of current state."""
        await self.state.save_checkpoint()

    async def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore to a previous checkpoint."""
        return await self.state.restore_checkpoint(checkpoint_id)

    async def get_status(self) -> Dict[str, Any]:
        """Get the current agent status."""
        session = self.state.current_session
        workflow = self.get_current_workflow()

        return {
            "running": self._running,
            "mode": self.mode_type.value,
            "session_id": session.session_id if session else None,
            "session_status": session.status.value if session else None,
            "workflow_running": self.is_workflow_running(),
            "workflow_paused": self.is_workflow_paused(),
            "workflow_progress": workflow.progress_percentage() if workflow else 0,
            "registered_tools": len(self.tools.list_tools()),
        }

    # --- Internal ---

    def _plan_to_workflow(self, plan: Plan) -> Workflow:
        """Convert a Plan to a Workflow for execution."""
        workflow = Workflow(
            workflow_id=plan.plan_id,
            name=plan.goal[:50],
            description=plan.goal,
        )

        for plan_step in plan.steps:
            step = WorkflowStep(
                step_id=plan_step.step_id,
                name=plan_step.description[:50],
                description=plan_step.description,
                step_type=StepType.ACTION,
                action_type=plan_step.action_type,
                parameters=plan_step.parameters,
                depends_on=plan_step.depends_on,
                max_retries=plan_step.max_retries,
                timeout_seconds=plan_step.timeout,
            )
            workflow.add_step(step)

        return workflow

    async def _auto_save_loop(self) -> None:
        """Periodically save agent state."""
        try:
            while self._running:
                await asyncio.sleep(15)  # Every 15 seconds
                await self.state.flush()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Auto-save error", error=str(e))
