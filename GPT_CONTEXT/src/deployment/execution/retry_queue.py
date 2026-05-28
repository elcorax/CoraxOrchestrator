"""
Corax Orchestrator - Retry Queue for Deferred Execution.

Manages a queue of failed operations that should be retried later.
Supports exponential backoff, max retry limits, and priority ordering.
The deployment MUST NOT stop when a tool fails - it continues and retries later.
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import time
import heapq

from src.core.logging import get_logger
from src.deployment.operations import (
    OperationTracker,
    OperationType,
    OperationStatus,
    FailureCategory,
)

logger = get_logger(__name__)


@dataclass
class RetryEntry:
    """An entry in the retry queue."""
    tool_key: str
    tool_name: str
    operation_id: str
    failure_category: FailureCategory
    error_message: str
    attempt: int = 0
    max_retries: int = 3
    next_retry_at: Optional[float] = None
    backoff_seconds: float = 5.0
    created_at: float = field(default_factory=time.time)
    last_attempt_at: Optional[float] = None
    skipped: bool = False

    @property
    def is_due(self) -> bool:
        """Check if this entry is due for retry."""
        if self.next_retry_at is None:
            return True
        return time.time() >= self.next_retry_at

    @property
    def is_exhausted(self) -> bool:
        """Check if max retries have been exhausted."""
        return self.attempt >= self.max_retries

    def calculate_backoff(self) -> float:
        """Calculate exponential backoff delay."""
        return self.backoff_seconds * (2 ** self.attempt)

    def mark_attempt(self) -> None:
        """Mark a retry attempt."""
        self.attempt += 1
        self.last_attempt_at = time.time()
        if not self.is_exhausted:
            self.next_retry_at = time.time() + self.calculate_backoff()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_key": self.tool_key,
            "tool_name": self.tool_name,
            "operation_id": self.operation_id,
            "failure_category": self.failure_category.value,
            "error_message": self.error_message[:200],
            "attempt": self.attempt,
            "max_retries": self.max_retries,
            "is_due": self.is_due,
            "is_exhausted": self.is_exhausted,
            "skipped": self.skipped,
        }


class RetryQueue:
    """
    Priority-based retry queue for failed deployment operations.

    Features:
    - Deferred retry execution (continues deployment, retries later)
    - Exponential backoff between retries
    - Per-tool max retry limits
    - Priority ordering (critical tools retried first)
    - Failure categorization for targeted retry strategies
    - Skip support for non-recoverable failures
    """

    def __init__(
        self,
        operation_tracker: Optional[OperationTracker] = None,
        default_max_retries: int = 3,
        default_backoff: float = 5.0,
    ) -> None:
        self._op_tracker = operation_tracker or OperationTracker()
        self._default_max_retries = default_max_retries
        self._default_backoff = default_backoff
        self._entries: Dict[str, RetryEntry] = {}
        self._priority_queue: List[tuple] = []
        self._completed_retries: List[RetryEntry] = []

    def add(
        self,
        tool_key: str,
        tool_name: str,
        operation_id: str,
        failure_category: FailureCategory,
        error_message: str,
        max_retries: Optional[int] = None,
        backoff_seconds: Optional[float] = None,
    ) -> None:
        """
        Add a failed operation to the retry queue.

        Args:
            tool_key: Tool identifier
            tool_name: Human-readable tool name
            operation_id: Original operation ID
            failure_category: Classification of the failure
            error_message: Error description
            max_retries: Maximum retry attempts (default: 3)
            backoff_seconds: Initial backoff in seconds (default: 5)
        """
        # Determine retry strategy based on failure category
        if failure_category == FailureCategory.PERMISSION:
            # Permission failures: retry fewer times with longer backoff
            max_retries = max_retries or 2
            backoff_seconds = backoff_seconds or 15.0
        elif failure_category == FailureCategory.NETWORK:
            # Network failures: retry more times with shorter backoff
            max_retries = max_retries or 4
            backoff_seconds = backoff_seconds or 3.0
        elif failure_category == FailureCategory.TEMPORARY:
            # Temporary failures: retry with moderate backoff
            max_retries = max_retries or 3
            backoff_seconds = backoff_seconds or 5.0
        elif failure_category == FailureCategory.DISK_SPACE:
            # Disk space: retry once (unlikely to resolve without intervention)
            max_retries = max_retries or 1
            backoff_seconds = backoff_seconds or 30.0
        elif failure_category == FailureCategory.DEPENDENCY:
            # Dependency failures: retry after dependencies are installed
            max_retries = max_retries or 3
            backoff_seconds = backoff_seconds or 10.0
        else:
            max_retries = max_retries or self._default_max_retries
            backoff_seconds = backoff_seconds or self._default_backoff

        entry = RetryEntry(
            tool_key=tool_key,
            tool_name=tool_name,
            operation_id=operation_id,
            failure_category=failure_category,
            error_message=error_message,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            next_retry_at=time.time(),  # Due immediately on first add
        )

        self._entries[tool_key] = entry
        # Priority: lower number = higher priority
        priority = self._get_category_priority(failure_category)
        heapq.heappush(self._priority_queue, (priority, time.time(), tool_key))

        logger.info(
            f"Added to retry queue",
            tool=tool_key,
            category=failure_category.value,
            max_retries=max_retries,
            backoff=backoff_seconds,
        )

    def _get_category_priority(self, category: FailureCategory) -> int:
        """Get retry priority for a failure category (lower = higher priority)."""
        priorities = {
            FailureCategory.TEMPORARY: 10,
            FailureCategory.NETWORK: 20,
            FailureCategory.DEPENDENCY: 30,
            FailureCategory.TIMEOUT: 40,
            FailureCategory.PERMISSION: 50,
            FailureCategory.DISK_SPACE: 60,
            FailureCategory.CORRUPTION: 70,
            FailureCategory.COMPATIBILITY: 80,
            FailureCategory.UNKNOWN: 90,
        }
        return priorities.get(category, 100)

    def get_due_entries(self) -> List[RetryEntry]:
        """Get all entries that are due for retry."""
        due = []
        remaining = []

        while self._priority_queue:
            priority, timestamp, tool_key = heapq.heappop(self._priority_queue)
            entry = self._entries.get(tool_key)
            if entry and not entry.is_exhausted and not entry.skipped and entry.is_due:
                due.append(entry)
            elif entry and not entry.skipped:
                remaining.append((priority, timestamp, tool_key))

        # Push remaining back
        for item in remaining:
            heapq.heappush(self._priority_queue, item)

        return due

    def has_pending(self) -> bool:
        """Check if there are any pending retries."""
        return any(
            not e.is_exhausted and not e.skipped
            for e in self._entries.values()
        )

    def has_due(self) -> bool:
        """Check if there are any due retries."""
        return any(
            not e.is_exhausted and not e.skipped and e.is_due
            for e in self._entries.values()
        )

    def mark_attempted(self, tool_key: str) -> None:
        """Mark a retry attempt for a tool."""
        entry = self._entries.get(tool_key)
        if entry:
            entry.mark_attempt()
            if not entry.is_exhausted:
                # Re-queue with updated priority
                priority = self._get_category_priority(entry.failure_category)
                heapq.heappush(
                    self._priority_queue,
                    (priority, time.time(), tool_key),
                )

    def mark_skipped(self, tool_key: str) -> None:
        """Mark a tool as skipped (non-recoverable failure)."""
        entry = self._entries.get(tool_key)
        if entry:
            entry.skipped = True
            logger.info(f"Marked {tool_key} as skipped in retry queue")

    def mark_completed(self, tool_key: str) -> None:
        """Mark a tool as successfully retried."""
        entry = self._entries.pop(tool_key, None)
        if entry:
            entry.skipped = True
            self._completed_retries.append(entry)

    def get_entry(self, tool_key: str) -> Optional[RetryEntry]:
        """Get the retry entry for a tool."""
        return self._entries.get(tool_key)

    def get_failed_tools(self) -> List[str]:
        """Get list of tool keys that have failed and are in the queue."""
        return [
            k for k, e in self._entries.items()
            if not e.skipped
        ]

    def get_exhausted_tools(self) -> List[RetryEntry]:
        """Get tools that have exhausted their retries."""
        return [
            e for e in self._entries.values()
            if e.is_exhausted and not e.skipped
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the retry queue state."""
        pending = [e for e in self._entries.values() if not e.is_exhausted and not e.skipped]
        exhausted = self.get_exhausted_tools()
        skipped = [e for e in self._entries.values() if e.skipped]

        return {
            "total_entries": len(self._entries),
            "pending_retries": len(pending),
            "exhausted": len(exhausted),
            "skipped": len(skipped),
            "completed_retries": len(self._completed_retries),
            "entries": [
                {
                    "tool_key": e.tool_key,
                    "attempt": e.attempt,
                    "max_retries": e.max_retries,
                    "category": e.failure_category.value,
                    "is_due": e.is_due,
                    "is_exhausted": e.is_exhausted,
                }
                for e in self._entries.values()
            ],
        }

    def clear(self) -> None:
        """Clear all retry entries."""
        self._entries.clear()
        self._priority_queue.clear()
        self._completed_retries.clear()
        logger.info("Retry queue cleared")
