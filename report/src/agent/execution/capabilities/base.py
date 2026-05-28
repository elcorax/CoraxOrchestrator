"""
Corax Orchestrator - Capability Base Classes.

Defines the abstract base for all execution capabilities and the
registry that manages them. Each capability represents a distinct
system execution ability the agent can use.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable, Type

from src.core.logging import get_logger

logger = get_logger(__name__)


class CapabilityError(Exception):
    """Base exception for capability execution errors."""

    def __init__(
        self,
        message: str,
        capability: str,
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.capability = capability
        self.recoverable = recoverable
        self.details = details or {}
        super().__init__(self.message)


@dataclass
class CapabilityResult:
    """
    Standard result from a capability execution.

    Provides a uniform result structure across all capabilities
    for consistent error handling and result processing.
    """
    success: bool
    capability: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "capability": self.capability,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "warnings": self.warnings,
        }


@dataclass
class ExecutionContext:
    """
    Context for capability execution.

    Carries session, permission, and configuration information
    needed for secure and tracked execution.
    """
    session_id: str
    mode: str = "safe"
    working_directory: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 300
    max_retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "working_directory": self.working_directory,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


class CapabilityBase(ABC):
    """
    Abstract base class for all execution capabilities.

    Each capability provides a specific system execution ability:
    - Terminal management
    - Process control
    - Installer interaction
    - Desktop automation
    - Browser automation
    - Sandbox enforcement
    - Recovery integration

    Capabilities are registered with the CapabilityRegistry and
    can be discovered and used by the agent runtime.
    """

    def __init__(self) -> None:
        self._initialized: bool = False
        self._context: Optional[ExecutionContext] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the unique name of this capability."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Get the version of this capability."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Get a description of what this capability provides."""
        ...

    @abstractmethod
    async def initialize(self, context: ExecutionContext) -> None:
        """
        Initialize the capability with an execution context.

        Args:
            context: The execution context for this session

        Raises:
            CapabilityError: If initialization fails
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the capability and release resources."""
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the capability is healthy and operational.

        Returns:
            Dict with health status information
        """
        ...

    @abstractmethod
    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """
        List the specific operations this capability provides.

        Returns:
            List of operation descriptors
        """
        ...

    @property
    def is_initialized(self) -> bool:
        """Check if the capability has been initialized."""
        return self._initialized

    @property
    def context(self) -> Optional[ExecutionContext]:
        """Get the current execution context."""
        return self._context

    def to_dict(self) -> Dict[str, Any]:
        """Serialize capability info to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "initialized": self._initialized,
        }


class CapabilityRegistry:
    """
    Registry for managing execution capabilities.

    Provides capability discovery, initialization, and lifecycle
    management. The agent runtime uses this to find and use
    capabilities.
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, CapabilityBase] = {}
        self._initialized: bool = False

    def register(self, capability: CapabilityBase) -> None:
        """
        Register a capability.

        Args:
            capability: The capability instance to register

        Raises:
            ValueError: If a capability with the same name exists
        """
        if capability.name in self._capabilities:
            raise ValueError(
                f"Capability '{capability.name}' is already registered"
            )
        self._capabilities[capability.name] = capability
        logger.info(
            "Capability registered",
            name=capability.name,
            version=capability.version,
        )

    def register_class(
        self,
        capability_class: Type[CapabilityBase],
    ) -> CapabilityBase:
        """
        Create and register a capability from its class.

        Args:
            capability_class: The capability class to instantiate

        Returns:
            The instantiated capability
        """
        instance = capability_class()
        self.register(instance)
        return instance

    async def initialize_all(self, context: ExecutionContext) -> None:
        """
        Initialize all registered capabilities.

        Args:
            context: The execution context for this session
        """
        if self._initialized:
            return

        for name, capability in self._capabilities.items():
            try:
                await capability.initialize(context)
                logger.info("Capability initialized", name=name)
            except Exception as e:
                logger.error(
                    "Failed to initialize capability",
                    name=name,
                    error=str(e),
                )

        self._initialized = True

    async def shutdown_all(self) -> None:
        """Shutdown all registered capabilities."""
        for name, capability in self._capabilities.items():
            try:
                await capability.shutdown()
                logger.info("Capability shut down", name=name)
            except Exception as e:
                logger.error(
                    "Failed to shutdown capability",
                    name=name,
                    error=str(e),
                )

        self._initialized = False

    def get(self, name: str) -> Optional[CapabilityBase]:
        """
        Get a capability by name.

        Args:
            name: The capability name

        Returns:
            The capability, or None if not found
        """
        return self._capabilities.get(name)

    def list_capabilities(self) -> List[Dict[str, Any]]:
        """
        List all registered capabilities.

        Returns:
            List of capability descriptors
        """
        return [
            cap.to_dict() for cap in self._capabilities.values()
        ]

    def get_operation_list(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all operations across all capabilities.

        Returns:
            Dict mapping capability names to their operations
        """
        return {
            name: cap.get_capabilities()
            for name, cap in self._capabilities.items()
        }

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Check health of all capabilities.

        Returns:
            Dict mapping capability names to health status
        """
        results = {}
        for name, capability in self._capabilities.items():
            try:
                results[name] = await capability.health_check()
            except Exception as e:
                results[name] = {
                    "healthy": False,
                    "error": str(e),
                }
        return results

    @property
    def count(self) -> int:
        """Get the number of registered capabilities."""
        return len(self._capabilities)

    @property
    def is_initialized(self) -> bool:
        """Check if all capabilities have been initialized."""
        return self._initialized

    def get_names(self) -> List[str]:
        """Get the names of all registered capabilities."""
        return list(self._capabilities.keys())
