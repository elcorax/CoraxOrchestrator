"""
Corax Orchestrator - Exception Hierarchy.

Defines a comprehensive exception hierarchy for the entire system,
enabling granular error handling and recovery strategies.
"""

from typing import Optional, Dict, Any


class CoraxError(Exception):
    """Base exception for all Corax Orchestrator errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = False,
    ) -> None:
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.recoverable = recoverable
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize exception to dictionary for reporting."""
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }


class ConfigurationError(CoraxError):
    """Raised when configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONFIG_ERROR",
            details={**(details or {}), "config_key": config_key},
            recoverable=True,
        )


class InstallationError(CoraxError):
    """Raised when a tool installation fails."""

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        exit_code: Optional[int] = None,
        output: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="INSTALL_ERROR",
            details={
                **(details or {}),
                "tool_name": tool_name,
                "exit_code": exit_code,
                "output": output,
            },
            recoverable=True,
        )


class DetectionError(CoraxError):
    """Raised when hardware/software detection fails."""

    def __init__(
        self,
        message: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DETECTION_ERROR",
            details={**(details or {}), "target": target},
            recoverable=True,
        )


class PermissionError(CoraxError):
    """Raised when insufficient permissions for an operation."""

    def __init__(
        self,
        message: str,
        required_privilege: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PERMISSION_ERROR",
            details={**(details or {}), "required_privilege": required_privilege},
            recoverable=True,
        )


class RecoveryError(CoraxError):
    """Raised when a self-healing recovery attempt fails."""

    def __init__(
        self,
        message: str,
        original_error: Optional[CoraxError] = None,
        recovery_attempts: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="RECOVERY_ERROR",
            details={
                **(details or {}),
                "original_error": str(original_error) if original_error else None,
                "recovery_attempts": recovery_attempts,
            },
            recoverable=False,
        )


class PlatformError(CoraxError):
    """Raised when a platform-specific operation is not supported."""

    def __init__(
        self,
        message: str,
        platform: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PLATFORM_ERROR",
            details={
                **(details or {}),
                "platform": platform,
                "operation": operation,
            },
            recoverable=False,
        )


class ModelError(CoraxError):
    """Raised when model management operations fail."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="MODEL_ERROR",
            details={
                **(details or {}),
                "model_name": model_name,
                "provider": provider,
            },
            recoverable=True,
        )


class PersistenceError(CoraxError):
    """Raised when state persistence operations fail."""

    def __init__(
        self,
        message: str,
        store: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PERSISTENCE_ERROR",
            details={
                **(details or {}),
                "store": store,
                "operation": operation,
            },
            recoverable=True,
        )
