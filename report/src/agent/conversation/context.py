"""
Corax Orchestrator - Context Window Manager.

Manages context windows for AI model interactions, handling
token limits, message truncation, and context summarization
to stay within model constraints.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContextWindow:
    """
    Represents a managed context window for AI model interactions.

    Tracks token usage and provides strategies for staying within
    model context limits.
    """
    max_tokens: int = 4096
    current_tokens: int = 0
    reserved_tokens: int = 512  # Reserved for response
    messages: List[Dict[str, Any]] = field(default_factory=list)
    strategy: str = "truncate"  # truncate, summarize, sliding

    @property
    def available_tokens(self) -> int:
        """Get available tokens for new content."""
        return self.max_tokens - self.current_tokens - self.reserved_tokens

    @property
    def is_full(self) -> bool:
        """Check if the context window is full."""
        return self.available_tokens <= 0

    @property
    def usage_ratio(self) -> float:
        """Get the current usage ratio (0.0 to 1.0)."""
        return self.current_tokens / self.max_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "current_tokens": self.current_tokens,
            "reserved_tokens": self.reserved_tokens,
            "available_tokens": self.available_tokens,
            "message_count": len(self.messages),
            "usage_ratio": round(self.usage_ratio, 3),
            "strategy": self.strategy,
        }


class ContextManager:
    """
    Manages context windows for AI model interactions.

    Features:
    - Token-aware context management
    - Multiple truncation strategies
    - Automatic context pruning
    - Token counting estimation
    - Context window tracking per session
    """

    def __init__(self, default_max_tokens: int = 4096) -> None:
        self.default_max_tokens = default_max_tokens
        self._windows: Dict[str, ContextWindow] = {}

    def get_or_create_window(
        self,
        session_id: str,
        max_tokens: Optional[int] = None,
        strategy: str = "truncate",
    ) -> ContextWindow:
        """
        Get or create a context window for a session.

        Args:
            session_id: The session identifier
            max_tokens: Maximum tokens for the window
            strategy: Truncation strategy

        Returns:
            ContextWindow for the session
        """
        if session_id not in self._windows:
            self._windows[session_id] = ContextWindow(
                max_tokens=max_tokens or self.default_max_tokens,
                strategy=strategy,
            )
        return self._windows[session_id]

    def update_token_count(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
    ) -> ContextWindow:
        """
        Update token count for a session's context window.

        Args:
            session_id: The session identifier
            messages: The messages to count tokens for

        Returns:
            Updated ContextWindow
        """
        window = self.get_or_create_window(session_id)
        window.messages = messages
        window.current_tokens = self._estimate_tokens(messages)
        return window

    def truncate_context(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Truncate messages to fit within the context window.

        Uses the configured strategy to reduce message count
        while preserving the most important context.

        Args:
            session_id: The session identifier
            messages: Messages to truncate
            max_tokens: Maximum tokens (uses window default if None)

        Returns:
            Truncated message list
        """
        window = self.get_or_create_window(session_id)
        max_tokens = max_tokens or window.max_tokens
        reserved = window.reserved_tokens
        available = max_tokens - reserved

        if self._estimate_tokens(messages) <= available:
            return messages

        if window.strategy == "truncate":
            return self._truncate_strategy(messages, available)
        elif window.strategy == "sliding":
            return self._sliding_window_strategy(messages, available)
        elif window.strategy == "summarize":
            return self._summarize_strategy(messages, available)
        else:
            return self._truncate_strategy(messages, available)

    def reset_window(self, session_id: str) -> None:
        """Reset the context window for a session."""
        if session_id in self._windows:
            del self._windows[session_id]

    def get_window_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get context window information for a session."""
        window = self._windows.get(session_id)
        return window.to_dict() if window else None

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Estimate token count for a list of messages.

        Uses a rough character-based estimation (4 chars ~= 1 token).
        """
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        # Add overhead for message structure (~20 tokens per message)
        overhead = len(messages) * 20
        return (total_chars // 4) + overhead

    def _truncate_strategy(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        Truncate strategy: keep system message and most recent messages.

        Preserves the system message (first message) and drops
        older messages until the context fits.
        """
        if not messages:
            return []

        # Always keep system message
        system_msg = None
        if messages[0].get("role") == "system":
            system_msg = messages[0]

        # Start from the end, keep as many as fit
        remaining = messages[1:] if system_msg else messages
        result = [system_msg] if system_msg else []

        # Work backwards to keep most recent messages
        for msg in reversed(remaining):
            test_messages = result + [msg]
            if self._estimate_tokens(test_messages) <= max_tokens:
                result.append(msg)
            else:
                break

        return result

    def _sliding_window_strategy(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        Sliding window strategy: keep a fixed-size window of messages.

        Maintains a sliding window of the most recent messages
        that fit within the token limit.
        """
        if not messages:
            return []

        # Keep system message
        system_msg = None
        if messages[0].get("role") == "system":
            system_msg = messages[0]

        remaining = messages[1:] if system_msg else messages
        result = [system_msg] if system_msg else []

        # Add messages from the end until we hit the limit
        for msg in reversed(remaining):
            test_messages = result + [msg]
            if self._estimate_tokens(test_messages) <= max_tokens:
                result.append(msg)
            else:
                break

        return result

    def _summarize_strategy(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        Summarize strategy: keep system message and recent messages,
        summarize older ones.

        Note: Actual summarization requires an AI model call.
        This implementation truncates as a fallback.
        """
        # For now, use truncation as the summarization strategy
        # Future: implement actual summarization via AI provider
        return self._truncate_strategy(messages, max_tokens)
