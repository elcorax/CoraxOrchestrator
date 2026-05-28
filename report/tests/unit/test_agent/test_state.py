"""
Tests for agent state management.

Tests session creation, persistence, checkpoints, and
state transitions.
"""

import pytest
from pathlib import Path
import tempfile
import json

from src.agent.state import (
    AgentState,
    AgentSession,
    AgentCheckpoint,
    AgentStatus,
)
from src.agent.modes.base import AgentModeType


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for persistence."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def agent_state(temp_dir: Path) -> AgentState:
    """Create an AgentState with temp persistence."""
    return AgentState(persistence_dir=temp_dir / "agent")


class TestAgentState:
    """Tests for AgentState management."""

    @pytest.mark.asyncio
    async def test_create_session(self, agent_state: AgentState):
        """Creating a session initializes state correctly."""
        session = await agent_state.create_session(
            session_id="test_session",
            mode=AgentModeType.SAFE,
        )

        assert session.session_id == "test_session"
        assert session.mode == AgentModeType.SAFE
        assert session.status == AgentStatus.IDLE
        assert agent_state.current_session is not None

    @pytest.mark.asyncio
    async def test_create_session_persists(self, agent_state: AgentState):
        """Session is persisted to disk on creation."""
        await agent_state.create_session(
            session_id="persist_test",
            mode=AgentModeType.ASSISTED,
        )

        # Check file exists
        session_file = agent_state.persistence_dir / "persist_test.json"
        assert session_file.exists()

        # Verify content
        with open(session_file, "r") as f:
            data = json.load(f)
        assert data["session_id"] == "persist_test"
        assert data["mode"] == "assisted"

    @pytest.mark.asyncio
    async def test_resume_session(self, agent_state: AgentState):
        """Resuming a session restores state correctly."""
        # Create session
        await agent_state.create_session(
            session_id="resume_test",
            mode=AgentModeType.AUTONOMOUS,
        )

        # Clear current session
        agent_state._current_session = None

        # Resume
        session = await agent_state.resume_session("resume_test")
        assert session is not None
        assert session.session_id == "resume_test"
        assert session.mode == AgentModeType.AUTONOMOUS
        assert session.status == AgentStatus.RUNNING

    @pytest.mark.asyncio
    async def test_resume_nonexistent_session(self, agent_state: AgentState):
        """Resuming a non-existent session returns None."""
        session = await agent_state.resume_session("nonexistent")
        assert session is None

    @pytest.mark.asyncio
    async def test_update_status(self, agent_state: AgentState):
        """Updating status changes session state."""
        await agent_state.create_session(session_id="status_test")
        await agent_state.update_status(AgentStatus.RUNNING)

        assert agent_state.current_session is not None
        assert agent_state.current_session.status == AgentStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_mode(self, agent_state: AgentState):
        """Updating mode changes session mode."""
        await agent_state.create_session(
            session_id="mode_test",
            mode=AgentModeType.SAFE,
        )
        await agent_state.update_mode(AgentModeType.AUTONOMOUS)

        assert agent_state.current_session is not None
        assert agent_state.current_session.mode == AgentModeType.AUTONOMOUS

    @pytest.mark.asyncio
    async def test_save_and_restore_checkpoint(self, agent_state: AgentState):
        """Checkpoints can be saved and restored."""
        await agent_state.create_session(session_id="checkpoint_test")

        # Save checkpoint
        cp = await agent_state.save_checkpoint()
        assert cp is not None
        assert cp.checkpoint_id is not None

        # Restore checkpoint
        result = await agent_state.restore_checkpoint(cp.checkpoint_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_restore_invalid_checkpoint(self, agent_state: AgentState):
        """Restoring an invalid checkpoint returns False."""
        await agent_state.create_session(session_id="invalid_cp_test")
        result = await agent_state.restore_checkpoint("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_record_execution(self, agent_state: AgentState):
        """Execution history is recorded."""
        await agent_state.create_session(session_id="history_test")

        await agent_state.record_execution({
            "event": "step_completed",
            "step_id": "step_1",
        })

        assert agent_state.current_session is not None
        assert len(agent_state.current_session.execution_history) == 1
        assert agent_state.current_session.execution_history[0]["event"] == "step_completed"

    @pytest.mark.asyncio
    async def test_record_error(self, agent_state: AgentState):
        """Errors are recorded."""
        await agent_state.create_session(session_id="error_test")

        await agent_state.record_error({
            "error": "Test error",
            "step_id": "step_1",
        })

        assert agent_state.current_session is not None
        assert len(agent_state.current_session.error_history) == 1

    @pytest.mark.asyncio
    async def test_update_metrics(self, agent_state: AgentState):
        """Metrics are updated."""
        await agent_state.create_session(session_id="metrics_test")

        await agent_state.update_metrics({
            "steps_completed": 5,
            "duration_seconds": 120,
        })

        assert agent_state.current_session is not None
        assert agent_state.current_session.metrics["steps_completed"] == 5
        assert agent_state.current_session.metrics["duration_seconds"] == 120

    @pytest.mark.asyncio
    async def test_list_sessions(self, agent_state: AgentState):
        """List sessions returns all persisted sessions."""
        await agent_state.create_session(session_id="list_test_1")
        await agent_state.create_session(session_id="list_test_2")

        sessions = await agent_state.list_sessions()
        assert "list_test_1" in sessions
        assert "list_test_2" in sessions

    @pytest.mark.asyncio
    async def test_archive_session(self, agent_state: AgentState):
        """Archiving a session removes it."""
        await agent_state.create_session(session_id="archive_test")

        result = await agent_state.archive_session("archive_test")
        assert result is True

        sessions = await agent_state.list_sessions()
        assert "archive_test" not in sessions

    @pytest.mark.asyncio
    async def test_flush(self, agent_state: AgentState):
        """Flush persists current state."""
        await agent_state.create_session(session_id="flush_test")
        await agent_state.update_status(AgentStatus.RUNNING)
        await agent_state.flush()

        # Verify persisted state
        session_file = agent_state.persistence_dir / "flush_test.json"
        assert session_file.exists()
        with open(session_file, "r") as f:
            data = json.load(f)
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_no_session_operations(self, agent_state: AgentState):
        """Operations without a session are no-ops."""
        # These should not raise errors
        await agent_state.update_status(AgentStatus.RUNNING)
        await agent_state.update_mode(AgentModeType.AUTONOMOUS)
        await agent_state.record_execution({"event": "test"})
        await agent_state.record_error({"error": "test"})
        await agent_state.update_metrics({"test": 1})
        await agent_state.flush()

        cp = await agent_state.save_checkpoint()
        assert cp is None
