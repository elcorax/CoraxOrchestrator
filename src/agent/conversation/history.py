"""
Corax Orchestrator - Conversation History.

Manages conversation history with persistence, search, and
context window management for agent interactions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
import json

from src.core.logging import get_logger
from src.agent.conversation.messages import (
    Message,
    MessageRole,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
)

logger = get_logger(__name__)


@dataclass
class ConversationEntry:
    """A single entry in the conversation history."""
    entry_id: str
    message: Message
    session_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "message": self.message.to_dict(),
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }


class ConversationHistory:
    """
    Manages conversation history for agent sessions.

    Features:
    - Append-only message storage
    - Session-scoped history
    - Persistence to disk
    - Search and filtering
    - Context window extraction
    - Token counting
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        max_history_per_session: int = 1000,
    ) -> None:
        self.storage_dir = storage_dir or Path("data/persistence/conversations")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_history_per_session = max_history_per_session
        self._entries: Dict[str, List[ConversationEntry]] = {}
        self._loaded_sessions: set = set()

    async def add_message(
        self,
        session_id: str,
        message: Message,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationEntry:
        """
        Add a message to the conversation history.

        Args:
            session_id: The session this message belongs to
            message: The message to add
            metadata: Optional metadata

        Returns:
            The created ConversationEntry
        """
        from uuid import uuid4

        entry = ConversationEntry(
            entry_id=str(uuid4()),
            message=message,
            session_id=session_id,
            metadata=metadata or {},
        )

        if session_id not in self._entries:
            self._entries[session_id] = []

        self._entries[session_id].append(entry)

        # Enforce max history
        if len(self._entries[session_id]) > self.max_history_per_session:
            self._entries[session_id] = (
                self._entries[session_id][-self.max_history_per_session:]
            )

        # Persist
        await self._persist_entry(entry)

        return entry

    async def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[ConversationEntry]:
        """
        Get conversation history for a session.

        Args:
            session_id: The session to get history for
            limit: Maximum number of entries
            offset: Number of entries to skip

        Returns:
            List of ConversationEntry objects
        """
        # Load from disk if not in memory
        if session_id not in self._entries:
            await self._load_session(session_id)

        entries = self._entries.get(session_id, [])
        if offset:
            entries = entries[offset:]
        if limit:
            entries = entries[:limit]
        return entries

    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Message]:
        """Get just the messages from a session's history."""
        entries = await self.get_history(session_id, limit, offset)
        return [entry.message for entry in entries]

    async def get_api_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get messages formatted for API calls."""
        messages = await self.get_messages(session_id, limit)
        return [msg.to_api_format() for msg in messages]

    async def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        role: Optional[MessageRole] = None,
    ) -> List[ConversationEntry]:
        """
        Search conversation history.

        Args:
            query: Text to search for
            session_id: Optional session filter
            role: Optional message role filter

        Returns:
            Matching ConversationEntry objects
        """
        results = []
        sessions = [session_id] if session_id else list(self._entries.keys())

        for sid in sessions:
            entries = self._entries.get(sid, [])
            for entry in entries:
                if query.lower() in entry.message.content.lower():
                    if role is None or entry.message.role == role:
                        results.append(entry)

        return results

    async def clear_session(self, session_id: str) -> bool:
        """Clear all history for a session."""
        self._entries.pop(session_id, None)
        session_file = self.storage_dir / f"{session_id}.jsonl"
        if session_file.exists():
            session_file.unlink()
        return True

    async def get_session_count(self) -> int:
        """Get the number of sessions with history."""
        return len(self._entries)

    async def get_message_count(self, session_id: str) -> int:
        """Get the message count for a session."""
        entries = self._entries.get(session_id, [])
        return len(entries)

    async def get_token_count(self, session_id: str) -> int:
        """Estimate token count for a session's messages."""
        entries = self._entries.get(session_id, [])
        total_chars = sum(len(e.message.content) for e in entries)
        return total_chars // 4  # Rough estimate

    async def _persist_entry(self, entry: ConversationEntry) -> None:
        """Persist a conversation entry to disk."""
        session_file = self.storage_dir / f"{entry.session_id}.jsonl"
        try:
            with open(session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as e:
            logger.error("Failed to persist conversation entry", error=str(e))

    async def _load_session(self, session_id: str) -> None:
        """Load a session's history from disk."""
        if session_id in self._loaded_sessions:
            return

        session_file = self.storage_dir / f"{session_id}.jsonl"
        if not session_file.exists():
            self._entries[session_id] = []
            self._loaded_sessions.add(session_id)
            return

        try:
            entries = []
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        msg_data = data.get("message", {})
                        role = MessageRole(msg_data.get("role", "user"))

                        message = self._create_message(role, msg_data)
                        entry = ConversationEntry(
                            entry_id=data["entry_id"],
                            message=message,
                            session_id=data["session_id"],
                            timestamp=data.get("timestamp", ""),
                        )
                        entries.append(entry)

            self._entries[session_id] = entries
            self._loaded_sessions.add(session_id)

        except Exception as e:
            logger.error("Failed to load session history", error=str(e))
            self._entries[session_id] = []

    def _create_message(self, role: MessageRole, data: Dict[str, Any]) -> Message:
        """Create the appropriate message type from data."""
        if role == MessageRole.SYSTEM:
            return SystemMessage(
                content=data.get("content", ""),
                message_id=data.get("message_id"),
                name=data.get("name"),
            )
        elif role == MessageRole.USER:
            return UserMessage(
                content=data.get("content", ""),
                message_id=data.get("message_id"),
                name=data.get("name"),
            )
        elif role == MessageRole.ASSISTANT:
            return AssistantMessage(
                content=data.get("content", ""),
                message_id=data.get("message_id"),
                name=data.get("name"),
                finish_reason=data.get("finish_reason", "stop"),
                usage=data.get("usage", {}),
            )
        elif role == MessageRole.TOOL:
            return ToolMessage(
                content=data.get("content", ""),
                message_id=data.get("message_id"),
                tool_call_id=data.get("tool_call_id", ""),
                tool_name=data.get("tool_name", ""),
            )
        return Message(role=role, content=data.get("content", ""))
