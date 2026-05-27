"""
Tests for the Execution Engine.

Tests workflow execution, pause/resume/cancel, step execution,
timeout handling, and retry logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio

from src.agent.execution.engine import ExecutionEngine
from src.agent.execution.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowStatus,
    StepType,
)
from src.agent.execution.context import ExecutionContext
from src.agent.state import AgentState
from src.agent.modes.base import AgentModeType
from pathlib import Path
import tempfile


@pytest.fixture
def temp_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def execution_engine(temp_dir: Path) -> ExecutionEngine:
    state = AgentState(persistence_dir=temp_dir / "agent")
    return ExecutionEngine(agent_state=state)


@pytest.fixture
def simple_workflow() -> Workflow:
    return Workflow(
        workflow_id="test_wf",
        name="Test Workflow",
        steps=[
            WorkflowStep(
                step_id="step_1",
                name="Step 1",
                action_type="test_action",
                description="First step",
            ),
            WorkflowStep(
                step_id="step_2",
                name="Step 2",
                action_type="test_action",
                description="Second step",
                depends_on=["step_1"],
            ),
        ],
    )


class TestExecutionEngine:
    """Tests for ExecutionEngine."""

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(
        self, execution_engine: ExecutionEngine, simple_workflow: Workflow
    ):
        """Simple workflow executes all steps."""
        result = await execution_engine.execute_workflow(simple_workflow)
        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_with_executor(
        self, execution_engine: ExecutionEngine, simple_workflow: Workflow
    ):
        """Steps with registered executors are called."""
        mock_executor = AsyncMock(return_value={"result": "ok"})
        execution_engine.register_step_executor("test_action", mock_executor)

        result = await execution_engine.execute_workflow(simple_workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert mock_executor.call_count == 2

    @pytest.mark.asyncio
    async def test_executor_receives_parameters(
        self, execution_engine: ExecutionEngine
    ):
        """Executor receives step parameters and context."""
        mock_executor = AsyncMock(return_value={"result": "ok"})
        execution_engine.register_step_executor("test_action", mock_executor)

        workflow = Workflow(
            workflow_id="param_test",
            name="Parameter Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Step 1",
                    action_type="test_action",
                    parameters={"key": "value"},
                ),
            ],
        )

        await execution_engine.execute_workflow(workflow)

        # Check executor was called with parameters
        call_kwargs = mock_executor.call_args[1]
        assert call_kwargs["parameters"] == {"key": "value"}
        assert call_kwargs["context"] is not None

    @pytest.mark.asyncio
    async def test_dependency_resolution(
        self, execution_engine: ExecutionEngine
    ):
        """Steps with dependencies execute in order."""
        execution_order = []

        async def executor_a(**kwargs):
            execution_order.append("A")

        async def executor_b(**kwargs):
            execution_order.append("B")

        async def executor_c(**kwargs):
            execution_order.append("C")

        execution_engine.register_step_executor("action_a", executor_a)
        execution_engine.register_step_executor("action_b", executor_b)
        execution_engine.register_step_executor("action_c", executor_c)

        workflow = Workflow(
            workflow_id="dep_test",
            name="Dependency Test",
            steps=[
                WorkflowStep(
                    step_id="step_a",
                    name="Step A",
                    action_type="action_a",
                ),
                WorkflowStep(
                    step_id="step_b",
                    name="Step B",
                    action_type="action_b",
                    depends_on=["step_a"],
                ),
                WorkflowStep(
                    step_id="step_c",
                    name="Step C",
                    action_type="action_c",
                    depends_on=["step_b"],
                ),
            ],
        )

        await execution_engine.execute_workflow(workflow)
        assert execution_order == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_pause_resume(
        self, execution_engine: ExecutionEngine
    ):
        """Workflow can be paused and resumed."""
        pause_event = asyncio.Event()

        async def slow_executor(**kwargs):
            pause_event.set()
            await asyncio.sleep(0.5)
            return {"result": "ok"}

        execution_engine.register_step_executor("slow_action", slow_executor)

        workflow = Workflow(
            workflow_id="pause_test",
            name="Pause Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Slow Step",
                    action_type="slow_action",
                ),
            ],
        )

        # Start execution
        task = asyncio.create_task(
            execution_engine.execute_workflow(workflow)
        )

        # Wait for step to start
        await pause_event.wait()
        await asyncio.sleep(0.1)

        # Pause
        await execution_engine.pause()
        assert execution_engine.is_paused()

        # Resume
        await execution_engine.resume()
        assert not execution_engine.is_paused()

        await task

    @pytest.mark.asyncio
    async def test_cancel(
        self, execution_engine: ExecutionEngine
    ):
        """Workflow can be cancelled."""
        pause_event = asyncio.Event()

        async def long_executor(**kwargs):
            pause_event.set()
            await asyncio.sleep(10)  # Long running
            return {"result": "ok"}

        execution_engine.register_step_executor("long_action", long_executor)

        workflow = Workflow(
            workflow_id="cancel_test",
            name="Cancel Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Long Step",
                    action_type="long_action",
                ),
            ],
        )

        task = asyncio.create_task(
            execution_engine.execute_workflow(workflow)
        )

        await pause_event.wait()
        await asyncio.sleep(0.1)

        await execution_engine.cancel()
        result = await task

        assert result.status == WorkflowStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_step_timeout(
        self, execution_engine: ExecutionEngine
    ):
        """Steps that timeout are marked as failed."""
        async def slow_executor(**kwargs):
            await asyncio.sleep(10)
            return {"result": "ok"}

        execution_engine.register_step_executor("slow_action", slow_executor)

        workflow = Workflow(
            workflow_id="timeout_test",
            name="Timeout Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Slow Step",
                    action_type="slow_action",
                    timeout_seconds=1,  # 1 second timeout
                ),
            ],
        )

        result = await execution_engine.execute_workflow(workflow)
        assert result.status == WorkflowStatus.FAILED
        assert result.steps[0].status == WorkflowStatus.FAILED
        assert "timed out" in (result.steps[0].error or "").lower()

    @pytest.mark.asyncio
    async def test_step_retry(
        self, execution_engine: ExecutionEngine
    ):
        """Failed steps are retried up to max_retries."""
        call_count = 0

        async def failing_executor(**kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Temporary failure")

        execution_engine.register_step_executor("failing_action", failing_executor)

        workflow = Workflow(
            workflow_id="retry_test",
            name="Retry Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Failing Step",
                    action_type="failing_action",
                    max_retries=2,
                ),
            ],
        )

        result = await execution_engine.execute_workflow(workflow)
        # Should have tried 3 times (1 initial + 2 retries)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_progress_callback(
        self, execution_engine: ExecutionEngine, simple_workflow: Workflow
    ):
        """Progress callbacks are invoked for each step."""
        progress_steps = []

        async def progress_cb(workflow: Workflow, step: WorkflowStep):
            progress_steps.append(step.step_id)

        execution_engine.on_progress(progress_cb)

        await execution_engine.execute_workflow(simple_workflow)

        assert len(progress_steps) == 2
        assert progress_steps == ["step_1", "step_2"]

    @pytest.mark.asyncio
    async def test_execution_context(
        self, execution_engine: ExecutionEngine
    ):
        """Execution context is available during step execution."""
        context_check = {}

        async def context_executor(**kwargs):
            context_check["ctx"] = kwargs.get("context")
            return {"result": "ok"}

        execution_engine.register_step_executor("ctx_action", context_executor)

        workflow = Workflow(
            workflow_id="ctx_test",
            name="Context Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Context Step",
                    action_type="ctx_action",
                ),
            ],
        )

        ctx = ExecutionContext(
            workflow_id="ctx_test",
            variables={"test_var": "test_value"},
        )

        await execution_engine.execute_workflow(workflow, context=ctx)

        assert context_check["ctx"] is not None
        assert context_check["ctx"].get_variable("test_var") == "test_value"

    @pytest.mark.asyncio
    async def test_workflow_progress_percentage(
        self, execution_engine: ExecutionEngine, simple_workflow: Workflow
    ):
        """Workflow progress percentage is calculated correctly."""
        result = await execution_engine.execute_workflow(simple_workflow)
        assert result.progress_percentage() == 100.0

    @pytest.mark.asyncio
    async def test_is_running(
        self, execution_engine: ExecutionEngine
    ):
        """is_running returns correct state."""
        assert not execution_engine.is_running()

        # Use a workflow with a slow executor to ensure we catch it running
        async def slow_executor(**kwargs):
            await asyncio.sleep(0.5)
            return {"result": "ok"}

        execution_engine.register_step_executor("slow_action", slow_executor)

        workflow = Workflow(
            workflow_id="running_test",
            name="Running Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Slow Step",
                    action_type="slow_action",
                ),
            ],
        )

        task = asyncio.create_task(
            execution_engine.execute_workflow(workflow)
        )
        await asyncio.sleep(0.1)
        assert execution_engine.is_running()

        await task
        assert not execution_engine.is_running()

    @pytest.mark.asyncio
    async def test_get_current_workflow(
        self, execution_engine: ExecutionEngine, simple_workflow: Workflow
    ):
        """get_current_workflow returns the executing workflow."""
        assert execution_engine.get_current_workflow() is None

        await execution_engine.execute_workflow(simple_workflow)
        assert execution_engine.get_current_workflow() is not None
        assert execution_engine.get_current_workflow().workflow_id == "test_wf"

    @pytest.mark.asyncio
    async def test_get_context(
        self, execution_engine: ExecutionEngine
    ):
        """get_context returns the execution context."""
        assert execution_engine.get_context() is None

        workflow = Workflow(
            workflow_id="ctx_get_test",
            name="Context Get Test",
            steps=[
                WorkflowStep(
                    step_id="step_1",
                    name="Step 1",
                    action_type="test_action",
                ),
            ],
        )

        ctx = ExecutionContext(workflow_id="ctx_get_test")
        await execution_engine.execute_workflow(workflow, context=ctx)

        retrieved_ctx = execution_engine.get_context()
        assert retrieved_ctx is not None
        assert retrieved_ctx.workflow_id == "ctx_get_test"
