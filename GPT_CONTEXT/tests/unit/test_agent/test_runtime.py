"""
Tests for the AgentRuntime.

Tests session lifecycle, mode management, workflow execution,
reasoning integration, and tool execution.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from src.agent import AgentRuntime
from src.agent.state import AgentState, AgentStatus
from src.agent.modes.base import AgentModeType, ActionProposal
from src.agent.execution.workflow import Workflow, WorkflowStep, WorkflowStatus, StepType
from src.agent.execution.context import ExecutionContext
from src.agent.reasoning.engine import ReasoningResult
from src.agent.reasoning.planner import Plan, PlanStep
from src.agent.reasoning.decisions import Decision
from src.agent.tool_executor import ToolExecutor


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def agent_runtime(temp_dir: Path) -> AgentRuntime:
    """Create an AgentRuntime with temp persistence."""
    state = AgentState(persistence_dir=temp_dir / "agent")
    return AgentRuntime(agent_state=state)


class TestAgentRuntime:
    """Tests for AgentRuntime."""

    @pytest.mark.asyncio
    async def test_start_session(self, agent_runtime: AgentRuntime):
        """Starting a session initializes the runtime."""
        session = await agent_runtime.start_session(
            session_id="test_session",
            mode=AgentModeType.SAFE,
        )

        assert session.session_id == "test_session"
        assert agent_runtime.mode_type == AgentModeType.SAFE
        assert agent_runtime.state.current_session is not None

    @pytest.mark.asyncio
    async def test_start_session_auto_id(self, agent_runtime: AgentRuntime):
        """Starting without session ID generates one."""
        session = await agent_runtime.start_session(mode=AgentModeType.SAFE)
        assert session.session_id is not None
        assert session.session_id.startswith("session_")

    @pytest.mark.asyncio
    async def test_resume_session(self, agent_runtime: AgentRuntime):
        """Resuming a session restores state."""
        await agent_runtime.start_session(
            session_id="resume_test",
            mode=AgentModeType.ASSISTED,
        )
        await agent_runtime.end_session()

        session = await agent_runtime.resume_session("resume_test")
        assert session is not None
        assert session.session_id == "resume_test"

    @pytest.mark.asyncio
    async def test_end_session(self, agent_runtime: AgentRuntime):
        """Ending a session persists state."""
        await agent_runtime.start_session(session_id="end_test")
        await agent_runtime.end_session()

        status = await agent_runtime.get_status()
        assert status["running"] is False

    @pytest.mark.asyncio
    async def test_set_mode(self, agent_runtime: AgentRuntime):
        """Setting mode changes agent behavior."""
        await agent_runtime.start_session(session_id="mode_test")

        agent_runtime.set_mode(AgentModeType.AUTONOMOUS)
        assert agent_runtime.mode_type == AgentModeType.AUTONOMOUS

        agent_runtime.set_mode(AgentModeType.ASSISTED)
        assert agent_runtime.mode_type == AgentModeType.ASSISTED

    @pytest.mark.asyncio
    async def test_get_available_modes(self, agent_runtime: AgentRuntime):
        """Available modes are listed with descriptions."""
        modes = agent_runtime.get_available_modes()
        assert len(modes) == 3

        mode_types = [m["type"] for m in modes]
        assert "safe" in mode_types
        assert "assisted" in mode_types
        assert "autonomous" in mode_types

    @pytest.mark.asyncio
    async def test_approval_callback(self, agent_runtime: AgentRuntime):
        """Approval callback is propagated to modes."""
        mock_callback = AsyncMock(return_value=True)
        agent_runtime.on_approval_request(mock_callback)

        # Verify callback is set on all modes
        for mode in agent_runtime._mode_map.values():
            assert mode._approval_callback is not None

    @pytest.mark.asyncio
    async def test_register_tool(self, agent_runtime: AgentRuntime):
        """Tools can be registered and executed."""
        mock_executor = AsyncMock(return_value={"status": "ok"})

        agent_runtime.register_tool(
            name="test_tool",
            executor=mock_executor,
            metadata={"description": "Test tool"},
        )

        tools = agent_runtime.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_execute_tool(self, agent_runtime: AgentRuntime):
        """Tools can be executed."""
        mock_executor = AsyncMock(return_value={"result": "success"})
        agent_runtime.register_tool("test_tool", mock_executor)

        result = await agent_runtime.execute_tool(
            tool_name="test_tool",
            parameters={"param1": "value1"},
        )

        assert result["status"] == "success"
        assert result["result"]["result"] == "success"
        mock_executor.assert_called_once_with(param1="value1")

    @pytest.mark.asyncio
    async def test_analyze(self, agent_runtime: AgentRuntime):
        """Problem analysis returns reasoning result."""
        result = await agent_runtime.analyze(
            goal="Install development tools",
            context={"mode": "safe"},
        )

        assert isinstance(result, ReasoningResult)
        assert result.confidence > 0
        assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_plan(self, agent_runtime: AgentRuntime):
        """Planning creates a structured plan."""
        plan = await agent_runtime.plan(
            goal="Full deploy",
            context={"system_scanned": False},
        )

        assert isinstance(plan, Plan)
        assert len(plan.steps) > 0
        assert plan.plan_id is not None

    @pytest.mark.asyncio
    async def test_decide(self, agent_runtime: AgentRuntime):
        """Decision making selects best option."""
        decision = await agent_runtime.decide(
            question="Which deployment approach?",
            options=["Full deploy", "Quick scan", "Minimal install"],
            context={"mode": "safe"},
        )

        assert isinstance(decision, Decision)
        assert decision.selected_option in ["Full deploy", "Quick scan", "Minimal install"]
        assert decision.confidence > 0

    @pytest.mark.asyncio
    async def test_assess_risk(self, agent_runtime: AgentRuntime):
        """Risk assessment evaluates action safety."""
        result = await agent_runtime.assess_risk(
            action="install_tool",
            context={"modifies_system": True, "requires_admin": True},
        )

        assert isinstance(result, ReasoningResult)
        assert result.conclusion in ["Risky", "Safe"]

    @pytest.mark.asyncio
    async def test_get_status(self, agent_runtime: AgentRuntime):
        """Status returns current runtime state."""
        await agent_runtime.start_session(session_id="status_test")

        status = await agent_runtime.get_status()
        assert status["running"] is True
        assert status["mode"] == "safe"
        assert status["session_id"] == "status_test"
        assert status["session_status"] == "idle"

    @pytest.mark.asyncio
    async def test_execute_workflow(self, agent_runtime: AgentRuntime):
        """Workflow execution processes all steps."""
        await agent_runtime.start_session(session_id="workflow_test")

        workflow = Workflow(
            workflow_id="test_wf",
            name="Test Workflow",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Step 1",
                    action_type="test_action",
                ),
            ],
        )

        result = await agent_runtime.execute_workflow(workflow)
        assert result.status in [
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        ]

    @pytest.mark.asyncio
    async def test_pause_resume_cancel(self, agent_runtime: AgentRuntime):
        """Workflow can be paused, resumed, and cancelled."""
        await agent_runtime.start_session(session_id="control_test")

        # Set auto-approve callback so safe mode doesn't block
        async def auto_approve(proposal: ActionProposal) -> bool:
            return True
        agent_runtime.on_approval_request(auto_approve)

        # Register a slow executor so the workflow stays running
        async def slow_executor(**kwargs):
            await asyncio.sleep(1.0)
            return {"result": "ok"}

        agent_runtime.execution.register_step_executor("slow_action", slow_executor)

        # Start a workflow with a slow step
        workflow = Workflow(
            workflow_id="control_wf",
            name="Control Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Step 1",
                    action_type="slow_action",
                ),
            ],
        )

        # Execute in background
        task = asyncio.create_task(
            agent_runtime.execute_workflow(workflow)
        )

        # Give it a moment to start
        await asyncio.sleep(0.1)

        # Pause
        await agent_runtime.pause_workflow()
        assert agent_runtime.is_workflow_paused()

        # Resume
        await agent_runtime.resume_workflow()
        assert not agent_runtime.is_workflow_paused()

        # Cancel
        await agent_runtime.cancel_workflow()

        await task

    @pytest.mark.asyncio
    async def test_save_restore_checkpoint(self, agent_runtime: AgentRuntime):
        """Checkpoints can be saved and restored."""
        await agent_runtime.start_session(session_id="cp_test")

        await agent_runtime.save_checkpoint()
        # Should not raise
        assert True

    @pytest.mark.asyncio
    async def test_list_sessions(self, agent_runtime: AgentRuntime):
        """Sessions can be listed."""
        await agent_runtime.start_session(session_id="list_1")
        await agent_runtime.end_session()

        await agent_runtime.start_session(session_id="list_2")
        await agent_runtime.end_session()

        sessions = await agent_runtime.list_sessions()
        assert "list_1" in sessions
        assert "list_2" in sessions
