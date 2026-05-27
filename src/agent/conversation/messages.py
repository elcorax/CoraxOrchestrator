"""
Corax Orchestrator - Message Types.

Defines message types and roles for agent conversations.
Supports system, user, assistant, and tool messages with
structured content.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class MessageRole(Enum):
    """Roles for conversation messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Base message in a conversation."""
    role: MessageRole
    content: str = ""
    message_id: Optional[str] = None
    name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "name": self.name,
        }

    def to_api_format(self) -> Dict[str, Any]:
        """Format message for API calls (OpenAI-compatible)."""
        msg = {"role": self.role.value, "content": self.content}
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class SystemMessage(Message):
    """System-level instruction message."""
    role: MessageRole = MessageRole.SYSTEM


@dataclass
class UserMessage(Message):
    """User input message."""
    role: MessageRole = MessageRole.USER


@dataclass
class AssistantMessage(Message):
    """Assistant response message."""
    role: MessageRole = MessageRole.ASSISTANT
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["finish_reason"] = self.finish_reason
        data["usage"] = self.usage
        return data


@dataclass
class ToolMessage(Message):
    """Tool execution result message."""
    role: MessageRole = MessageRole.TOOL
    tool_call_id: str = ""
    tool_name: str = ""
    tool_result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["tool_call_id"] = self.tool_call_id
        data["tool_name"] = self.tool_name
        return data

    def to_api_format(self) -> Dict[str, Any]:
        return {
            "role": "tool",
            "content": self.content,
            "tool_call_id": self.tool_call_id,
        }
