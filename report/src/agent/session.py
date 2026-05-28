"""
Corax Orchestrator - Session Management.

Manages agent sessions including creation, lifecycle, persistence,
and state tracking across sessions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
from uuid import uuid4

from src.core.logging import get_logger
from src.agent.modes.base import AgentModeType
from src.agent.state import AgentState, AgentStatus

logger = get_logger(__name__)


@dataclass
class AgentSession:
    """
    Represents a single agent session.

    A session encapsulates a complete agent interaction from
    creation to termination, including mode, configuration,
    and state tracking.
    """
    session_id: str
    mode: AgentModeType = AgentModeType.SAFE
    status: AgentStatus = AgentStatus.IDLE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    configuration: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "configuration": self.configuration,
        }


class SessionManager:
    """
    Manages agent session lifecycle.

    Features:
    - Session creation and configuration
    - Session persistence to disk
    - Session resumption after restart
    - Session listing and search
    - Automatic cleanup of old sessions
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        agent_state: Optional[AgentState] = None,
    ) -> None:
        self.storage_dir = storage_dir or Path("data/persistence/sessions")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.agent_state = agent_state or AgentState()
        self._sessions: Dict[str, AgentSession] = {}
        self._current_session_id: Optional[str] = None

    @property
    def current_session(self) -> Optional[AgentSession]:
        """Get the current active session."""
        if self._current_session_id:
            return self._sessions.get(self._current_session_id)
        return None

    @property
    def current_session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._current_session_id

    async def create_session(
        self,
        session_id: Optional[str] = None,
        mode: AgentModeType = AgentModeType.SAFE,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> AgentSession:
        """
        Create a new agent session.

        Args:
            session_id: Optional custom session ID
            mode: Initial agent mode
            configuration: Optional session configuration

        Returns:
            The created AgentSession
        """
        session = AgentSession(
            session_id=session_id or f"session_{uuid4().hex[:8]}",
            mode=mode,
            configuration=configuration or {},
        )

        self._sessions[session.session_id] = session
        self._current_session_id = session.session_id

        await self._persist_session(session)
        await self.agent_state.create_session(
            session_id=session.session_id,
            mode=mode,
            configuration=configuration,
        )

        logger.info(
            "Session created",
            session_id=session.session_id,
            mode=mode.value,
        )

        return session

    async def resume_session(self, session_id: str) -> Optional[AgentSession]:
        """
        Resume a previous session.

        Args:
            session_id: The session to resume

        Returns:
            The resumed AgentSession, or None if not found
        """
        session = await self._load_session(session_id)
        if session:
            self._sessions[session_id] = session
            self._current_session_id = session_id
            session.status = AgentStatus.RUNNING
            session.updated_at = datetime.now(timezone.utc).isoformat()

            await self.agent_state.resume_session(session_id)

            logger.info("Session resumed", session_id=session_id)
            return session

        logger.warning("Session not found for resume", session_id=session_id)
        return None

    async def end_session(self, session_id: Optional[str] = None) -> bool:
        """
        End a session.

        Args:
            session_id: Session to end (uses current if None)

        Returns:
            True if successful
        """
        sid = session_id or self._current_session_id
        if not sid or sid not in self._sessions:
            return False

        session = self._sessions[sid]
        session.status = AgentStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc).isoformat()
        session.updated_at = datetime.now(timezone.utc).isoformat()

        await self._persist_session(session)
        await self.agent_state.update_status(AgentStatus.COMPLETED)

        if self._current_session_id == sid:
            self._current_session_id = None

        logger.info("Session ended", session_id=sid)
        return True

    async def list_sessions(
        self,
        limit: int = 50,
        status: Optional[AgentStatus] = None,
    ) -> List[AgentSession]:
        """
        List all sessions.

        Args:
            limit: Maximum number of sessions to return
            status: Optional status filter

        Returns:
            List of AgentSession objects
        """
        sessions = list(self._sessions.values())

        if status:
            sessions = [s for s in sessions if s.status == status]

        # Also load from disk
        for session_file in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]:
            sid = session_file.stem
            if sid not in self._sessions:
                session = await self._load_session(sid)
                if session:
                    if status is None or session.status == status:
                        sessions.append(session)

        return sessions[:limit]

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """Get a specific session by ID."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        return await self._load_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        self._sessions.pop(session_id, None)
        session_file = self.storage_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            return True
        return False

    async def update_session_config(
        self,
        session_id: str,
        configuration: Dict[str, Any],
    ) -> Optional[AgentSession]:
        """Update a session's configuration."""
        session = await self.get_session(session_id)
        if session:
            session.configuration.update(configuration)
            session.updated_at = datetime.now(timezone.utc).isoformat()
            await self._persist_session(session)
            return session
        return None

    async def _persist_session(self, session: AgentSession) -> None:
        """Persist a session to disk."""
        session_file = self.storage_dir / f"{session.session_id}.json"
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2)
        except Exception as e:
            logger.error("Failed to persist session", error=str(e))

    async def _load_session(self, session_id: str) -> Optional[AgentSession]:
        """Load a session from disk."""
        session_file = self.storage_dir / f"{session_id}.json"
        if not session_file.exists():
            return None

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return AgentSession(
                session_id=data["session_id"],
                mode=AgentModeType(data.get("mode", "safe")),
                status=AgentStatus(data.get("status", "idle")),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                completed_at=data.get("completed_at"),
                configuration=data.get("configuration", {}),
            )
        except Exception as e:
            logger.error("Failed to load session", session_id=session_id, error=str(e))
            return None
