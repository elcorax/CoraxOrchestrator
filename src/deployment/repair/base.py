"""
Corax Orchestrator - Repair Base.

Defines repair actions and results for the self-healing
deployment repair system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime


class RepairStatus(Enum):
    """Status of a repair action."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class RepairAction:
    """
    A single repair action to execute.

    Attributes:
        name: Action name
        description: Human-readable description
        handler: Async callable to execute the repair
        priority: Priority (higher = more important)
        timeout: Maximum execution time in seconds
        retry_count: Number of retries on failure
        max_retries: Maximum retry attempts
    """
    name: str
    description: str
    handler: Optional[Callable[[], Awaitable[bool]]] = None
    priority: int = 0
    timeout: int = 120
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class RepairResult:
    """
    Result of a repair action.

    Attributes:
        action_name: Name of the repair action
        status: Repair status
        message: Human-readable result
        details: Additional repair details
        timestamp: When repair was attempted
        duration_ms: How long repair took
        retry_count: Number of retries used
    """
    action_name: str
    status: RepairStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    retry_count: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status == RepairStatus.SUCCEEDED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
        }
