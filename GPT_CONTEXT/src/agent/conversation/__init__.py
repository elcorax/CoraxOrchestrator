"""
Corax Orchestrator - Conversation Management.

Manages conversation history, context windows, and message threading
for the agent's interactions with users and AI models.

Architecture:
    conversation/
    ├── __init__.py          # Package exports
    ├── history.py           # Conversation history management
    ├── context.py           # Context window management
    └── messages.py          # Message types and formatting
"""

from src.agent.conversation.history import ConversationHistory, ConversationEntry
from src.agent.conversation.context import ContextManager, ContextWindow
from src.agent.conversation.messages import (
    Message,
    MessageRole,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
)

__all__ = [
    "ConversationHistory",
    "ConversationEntry",
    "ContextManager",
    "ContextWindow",
    "Message",
    "MessageRole",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
]
