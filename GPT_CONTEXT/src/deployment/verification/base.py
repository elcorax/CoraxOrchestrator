"""
Corax Orchestrator - Verification Base.

Defines verification results and status types for
AI infrastructure health checks.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime


class VerificationStatus(Enum):
    """Status of a verification check."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class VerificationResult:
    """
    Result of a verification check.

    Attributes:
        check_name: Name of the check performed
        status: Verification status
        message: Human-readable result message
        details: Additional check details
        timestamp: When the check was performed
        duration_ms: How long the check took
        suggestions: List of improvement suggestions
    """
    check_name: str
    status: VerificationStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    suggestions: List[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.status == VerificationStatus.HEALTHY

    @property
    def is_degraded(self) -> bool:
        return self.status == VerificationStatus.DEGRADED

    @property
    def is_unhealthy(self) -> bool:
        return self.status == VerificationStatus.UNHEALTHY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "suggestions": self.suggestions,
        }
