"""
Corax Orchestrator - Agent State Management.

Manages persistent and in-memory state for the autonomous agent,
including execution history, checkpoints, and configuration.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import json
import asyncio

from src.core.logging import get_logger
from src.core.exceptions import PersistenceError
from src.agent.modes.base import AgentModeType

logger = get_logger(__name__)


class AgentStatus(Enum):
    """Overall status of the agent runtime."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentCheckpoint:
    """
    A snapshot of agent state at a point in time.

    Checkpoints enable pause/resume and rollback capabilities.
    """
    checkpoint_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_status: AgentStatus = AgentStatus.IDLE
    current_workflow_id: Optional[str] = None
    current_step_index: int = 0
    execution_context: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    completed_steps: List[str] = field(default_factory=list)
    pending_decisions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "agent_status": self.agent_status.value,
            "current_workflow_id": self.current_workflow_id,
            "current_step_index": self.current_step_index,
            "execution_context": self.execution_context,
            "variables": self.variables,
            "completed_steps": self.completed_steps,
            "pending_decisions": self.pending_decisions,
            "metadata": self.metadata,
        }


@dataclass
class AgentSession:
    """
    A complete agent session with full state.

    Sessions persist across restarts and contain all information
    needed to resume execution.
    """
    session_id: str
    mode: AgentModeType = AgentModeType.SAFE
    status: AgentStatus = AgentStatus.IDLE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checkpoints: List[AgentCheckpoint] = field(default_factory=list)
    current_checkpoint_id: Optional[str] = None
    configuration: Dict[str, Any] = field(default_factory=dict)
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    error_history: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "current_checkpoint_id": self.current_checkpoint_id,
            "configuration": self.configuration,
            "execution_history": self.execution_history[-100:],  # Keep last 100
            "error_history": self.error_history[-50:],  # Keep last 50
            "metrics": self.metrics,
        }


class AgentState:
    """
    Manages agent state including persistence, checkpoints, and sessions.

    Provides:
    - Session management with create/resume/archive
    - Checkpoint-based pause/resume
    - Execution history tracking
    - Configuration persistence
    - Metrics collection
    """

    def __init__(self, persistence_dir: Optional[Path] = None) -> None:
        self.persistence_dir = persistence_dir or Path("data/persistence/agent")
        self.persistence_dir.mkdir(parents=True, exist_ok=True)

        self._current_session: Optional[AgentSession] = None
        self._lock = asyncio.Lock()
        self._dirty: bool = False
        self._auto_save_interval: int = 15  # seconds

    @property
    def current_session(self) -> Optional[AgentSession]:
        """Get the current active session."""
        return self._current_session

    async def create_session(
        self,
        session_id: str,
        mode: AgentModeType = AgentModeType.SAFE,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> AgentSession:
        """
        Create a new agent session.

        Args:
            session_id: Unique session identifier
            mode: Initial agent mode
            configuration: Optional session configuration

        Returns:
            New AgentSession
        """
        async with self._lock:
            session = AgentSession(
                session_id=session_id,
                mode=mode,
                configuration=configuration or {},
            )
            self._current_session = session
            self._dirty = True
            await self._persist_session()
            logger.info(
                "Agent session created",
                session_id=session_id,
                mode=mode.value,
            )
            return session

    async def resume_session(self, session_id: str) -> Optional[AgentSession]:
        """
        Resume a previously persisted session.

        Args:
            session_id: Session identifier to resume

        Returns:
            AgentSession if found, None otherwise
        """
        async with self._lock:
            session = await self._load_session(session_id)
            if session:
                session.status = AgentStatus.RUNNING
                session.updated_at = datetime.now(timezone.utc).isoformat()
                self._current_session = session
                self._dirty = True
                logger.info(
                    "Agent session resumed",
                    session_id=session_id,
                    mode=session.mode.value,
                )
            return session

    async def save_checkpoint(self) -> Optional[AgentCheckpoint]:
        """
        Create a checkpoint of the current session state.

        Returns:
            AgentCheckpoint if session is active, None otherwise
        """
        if not self._current_session:
            return None

        async with self._lock:
            from uuid import uuid4

            checkpoint = AgentCheckpoint(
                checkpoint_id=str(uuid4()),
                agent_status=self._current_session.status,
                current_workflow_id=self._get_current_workflow_id(),
                current_step_index=self._get_current_step_index(),
                execution_context=self._build_execution_context(),
                variables=self._get_variables(),
                completed_steps=self._get_completed_steps(),
                pending_decisions=self._get_pending_decisions(),
            )

            self._current_session.checkpoints.append(checkpoint)
            self._current_session.current_checkpoint_id = checkpoint.checkpoint_id
            self._dirty = True
            await self._persist_session()

            logger.debug(
                "Checkpoint saved",
                checkpoint_id=checkpoint.checkpoint_id,
                step=checkpoint.current_step_index,
            )

            return checkpoint

    async def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Restore agent state to a previous checkpoint.

        Args:
            checkpoint_id: Checkpoint to restore to

        Returns:
            True if restored successfully
        """
        if not self._current_session:
            return False

        async with self._lock:
            for i, cp in enumerate(self._current_session.checkpoints):
                if cp.checkpoint_id == checkpoint_id:
                    # Remove checkpoints after this one
                    self._current_session.checkpoints = (
                        self._current_session.checkpoints[: i + 1]
                    )
                    self._current_session.current_checkpoint_id = checkpoint_id
                    self._current_session.status = AgentStatus.PAUSED
                    self._dirty = True
                    await self._persist_session()
                    logger.info(
                        "Checkpoint restored",
                        checkpoint_id=checkpoint_id,
                    )
                    return True
            return False

    async def update_status(self, status: AgentStatus) -> None:
        """Update the current session status."""
        if not self._current_session:
            return
        async with self._lock:
            self._current_session.status = status
            self._current_session.updated_at = datetime.now(timezone.utc).isoformat()
            self._dirty = True

    async def update_mode(self, mode: AgentModeType) -> None:
        """Update the current agent mode."""
        if not self._current_session:
            return
        async with self._lock:
            self._current_session.mode = mode
            self._current_session.updated_at = datetime.now(timezone.utc).isoformat()
            self._dirty = True
            logger.info("Agent mode changed", mode=mode.value)

    async def record_execution(
        self, entry: Dict[str, Any]
    ) -> None:
        """Record an execution history entry."""
        if not self._current_session:
            return
        async with self._lock:
            entry["timestamp"] = entry.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            )
            self._current_session.execution_history.append(entry)
            self._dirty = True

    async def record_error(self, error: Dict[str, Any]) -> None:
        """Record an error occurrence."""
        if not self._current_session:
            return
        async with self._lock:
            error["timestamp"] = error.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            )
            self._current_session.error_history.append(error)
            self._dirty = True

    async def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Update session metrics."""
        if not self._current_session:
            return
        async with self._lock:
            self._current_session.metrics.update(metrics)
            self._dirty = True

    async def flush(self) -> None:
        """Force persist current state to disk."""
        if self._dirty and self._current_session:
            async with self._lock:
                await self._persist_session()
                self._dirty = False

    async def list_sessions(self) -> List[str]:
        """List all persisted session IDs."""
        sessions = []
        for f in self.persistence_dir.glob("*.json"):
            sessions.append(f.stem)
        return sorted(sessions)

    async def archive_session(self, session_id: str) -> bool:
        """Archive (delete) a session."""
        session_path = self.persistence_dir / f"{session_id}.json"
        if session_path.exists():
            session_path.unlink()
            if (
                self._current_session
                and self._current_session.session_id == session_id
            ):
                self._current_session = None
            return True
        return False

    async def _persist_session(self) -> None:
        """Persist the current session to disk."""
        if not self._current_session:
            return
        session_path = self.persistence_dir / f"{self._current_session.session_id}.json"
        temp_path = session_path.with_suffix(".tmp.json")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._current_session.to_dict(), f, indent=2, default=str)
            temp_path.replace(session_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise PersistenceError(
                message=f"Failed to persist agent session: {e}",
                store=str(self.persistence_dir),
                operation="write",
            )

    async def _load_session(self, session_id: str) -> Optional[AgentSession]:
        """Load a session from disk."""
        session_path = self.persistence_dir / f"{session_id}.json"
        if not session_path.exists():
            return None

        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            session = AgentSession(
                session_id=data["session_id"],
                mode=AgentModeType(data.get("mode", AgentModeType.SAFE.value)),
                status=AgentStatus(data.get("status", AgentStatus.IDLE.value)),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                configuration=data.get("configuration", {}),
                execution_history=data.get("execution_history", []),
                error_history=data.get("error_history", []),
                metrics=data.get("metrics", {}),
            )

            # Restore checkpoints
            for cp_data in data.get("checkpoints", []):
                checkpoint = AgentCheckpoint(
                    checkpoint_id=cp_data["checkpoint_id"],
                    timestamp=cp_data.get("timestamp", ""),
                    agent_status=AgentStatus(
                        cp_data.get("agent_status", AgentStatus.IDLE.value)
                    ),
                    current_workflow_id=cp_data.get("current_workflow_id"),
                    current_step_index=cp_data.get("current_step_index", 0),
                    execution_context=cp_data.get("execution_context", {}),
                    variables=cp_data.get("variables", {}),
                    completed_steps=cp_data.get("completed_steps", []),
                    pending_decisions=cp_data.get("pending_decisions", []),
                    metadata=cp_data.get("metadata", {}),
                )
                session.checkpoints.append(checkpoint)

            session.current_checkpoint_id = data.get("current_checkpoint_id")
            return session

        except Exception as e:
            logger.error(
                "Failed to load agent session",
                session_id=session_id,
                error=str(e),
            )
            return None

    def _get_current_workflow_id(self) -> Optional[str]:
        """Get the current workflow ID from execution context."""
        # This will be populated by the execution engine
        return None

    def _get_current_step_index(self) -> int:
        """Get the current step index."""
        return 0

    def _build_execution_context(self) -> Dict[str, Any]:
        """Build the current execution context for checkpointing."""
        return {}

    def _get_variables(self) -> Dict[str, Any]:
        """Get current workflow variables."""
        return {}

    def _get_completed_steps(self) -> List[str]:
        """Get list of completed step IDs."""
        return []

    def _get_pending_decisions(self) -> List[str]:
        """Get list of pending decision IDs."""
        return []
