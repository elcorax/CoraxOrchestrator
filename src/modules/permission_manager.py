"""
Corax Orchestrator - Permission Manager Module.

Manages permission checks, privilege escalation, and user consent
for operations that require elevated access.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Callable

from src.core.logging import get_logger
from src.core.exceptions import PermissionError
from src.platform.factory import PlatformFactory
from src.platform.base import PlatformBase

logger = get_logger(__name__)


class PermissionLevel(Enum):
    """Levels of permission required for operations."""
    NONE = "none"
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


@dataclass
class PermissionRequest:
    """A request for permission to perform an operation."""
    operation: str
    description: str
    level: PermissionLevel
    tool_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    granted: bool = False
    auto_granted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "description": self.description,
            "level": self.level.value,
            "tool_name": self.tool_name,
            "details": self.details,
            "granted": self.granted,
            "auto_granted": self.auto_granted,
        }


class PermissionManager:
    """
    Manages permissions and privilege escalation.

    Handles:
    - Checking if the current process has required privileges
    - Requesting user consent for operations
    - Auto-granting permissions based on configuration
    - Tracking permission history
    """

    def __init__(
        self,
        platform: Optional[PlatformBase] = None,
        auto_accept: bool = False,
    ) -> None:
        self.platform = platform or PlatformFactory.create()
        self.auto_accept = auto_accept
        self._permission_history: List[PermissionRequest] = []
        self._consent_callback: Optional[Callable[[PermissionRequest], bool]] = None

    def set_consent_callback(
        self, callback: Callable[[PermissionRequest], bool]
    ) -> None:
        """
        Set a callback for user consent requests.

        Args:
            callback: Function that takes a PermissionRequest and returns bool
        """
        self._consent_callback = callback

    def check_permission(self, level: PermissionLevel) -> bool:
        """
        Check if the current process has the required permission level.

        Args:
            level: Required permission level

        Returns:
            True if the process has sufficient permissions
        """
        if level == PermissionLevel.NONE:
            return True

        if level == PermissionLevel.USER:
            return True  # Always have user-level permissions

        if level == PermissionLevel.ADMIN:
            return self.platform.is_admin()

        if level == PermissionLevel.SYSTEM:
            # System level requires admin on most platforms
            return self.platform.is_admin()

        return False

    async def request_permission(
        self,
        operation: str,
        description: str,
        level: PermissionLevel = PermissionLevel.USER,
        tool_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> PermissionRequest:
        """
        Request permission for an operation.

        Args:
            operation: Operation identifier
            description: Human-readable description
            level: Required permission level
            tool_name: Optional tool name associated with the operation
            details: Additional details about the request

        Returns:
            PermissionRequest with granted status

        Raises:
            PermissionError: If permission is denied
        """
        request = PermissionRequest(
            operation=operation,
            description=description,
            level=level,
            tool_name=tool_name,
            details=details or {},
        )

        # Check if we already have the required permission level
        if self.check_permission(level):
            request.granted = True
            request.auto_granted = True
            self._permission_history.append(request)
            return request

        # Auto-accept if configured
        if self.auto_accept:
            request.granted = True
            request.auto_granted = True
            logger.info(
                "Permission auto-granted",
                operation=operation,
                level=level.value,
            )
            self._permission_history.append(request)
            return request

        # Request consent from user
        if self._consent_callback:
            request.granted = self._consent_callback(request)
        else:
            # No consent callback configured, deny by default
            request.granted = False

        self._permission_history.append(request)

        if not request.granted:
            raise PermissionError(
                message=f"Permission denied: {description}",
                required_privilege=level.value,
                details={"operation": operation, "tool_name": tool_name},
            )

        logger.info(
            "Permission granted",
            operation=operation,
            level=level.value,
        )
        return request

    async def request_elevation(
        self,
        operation: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Request admin elevation for an operation.

        Args:
            operation: Operation identifier
            description: Human-readable description
            details: Additional details

        Returns:
            True if elevation was granted/performed
        """
        try:
            request = await self.request_permission(
                operation=operation,
                description=description,
                level=PermissionLevel.ADMIN,
                details=details,
            )
            return request.granted
        except PermissionError:
            return False

    def get_history(self) -> List[PermissionRequest]:
        """Get the history of all permission requests."""
        return list(self._permission_history)

    def get_history_for_tool(self, tool_name: str) -> List[PermissionRequest]:
        """Get permission history for a specific tool."""
        return [
            r for r in self._permission_history
            if r.tool_name == tool_name
        ]

    def reset_history(self) -> None:
        """Clear permission history."""
        self._permission_history.clear()
