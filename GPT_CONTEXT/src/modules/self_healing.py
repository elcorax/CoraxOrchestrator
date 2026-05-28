"""
Corax Orchestrator - Self-Healing Engine Module.

Provides automatic error recovery, retry logic, and health monitoring
for deployment operations. Detects failures and attempts to recover
using configurable strategies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio

from src.core.logging import get_logger
from src.core.exceptions import CoraxError, RecoveryError

logger = get_logger(__name__)


class RecoveryStrategy(Enum):
    """Available recovery strategies."""
    RETRY = "retry"
    RESTART_SERVICE = "restart_service"
    REINSTALL = "reinstall"
    CLEAN_CACHE = "clean_cache"
    ESCALATE_PRIVILEGES = "escalate_privileges"
    SKIP = "skip"


@dataclass
class HealthStatus:
    """Health status of a component or operation."""
    healthy: bool = True
    last_check: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    strategy: RecoveryStrategy
    attempt_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    success: bool = False
    error: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "strategy": self.strategy.value,
            "attempt_number": self.attempt_number,
            "success": self.success,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    recovered: bool = False
    strategy_used: Optional[RecoveryStrategy] = None
    attempts: List[RecoveryAttempt] = field(default_factory=list)
    final_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovered": self.recovered,
            "strategy_used": self.strategy_used.value if self.strategy_used else None,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_error": self.final_error,
        }


class SelfHealingEngine:
    """
    Self-healing engine for automatic error recovery.

    Monitors operations for failures and applies configurable
    recovery strategies. Supports custom recovery handlers and
    tracks recovery history for analysis.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_retries: int = 3,
        retry_delay: int = 5,
        health_check_interval: int = 60,
    ) -> None:
        self.enabled = enabled
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_check_interval = health_check_interval
        self._recovery_history: List[RecoveryResult] = []
        self._custom_handlers: Dict[str, Callable[..., Awaitable[bool]]] = {}
        self._health_status: Dict[str, HealthStatus] = {}
        self._monitoring_task: Optional[asyncio.Task] = None

    async def attempt_recovery(
        self,
        error: CoraxError,
        context: Optional[Dict[str, Any]] = None,
    ) -> RecoveryResult:
        """
        Attempt to recover from an error.

        Args:
            error: The error to recover from
            context: Additional context about the error

        Returns:
            RecoveryResult with recovery outcome
        """
        result = RecoveryResult()
        context = context or {}

        if not self.enabled:
            logger.info("Self-healing is disabled, skipping recovery")
            result.final_error = "Self-healing disabled"
            return result

        logger.info(
            "Attempting recovery",
            error_code=error.code,
            recoverable=error.recoverable,
        )

        if not error.recoverable:
            logger.warning("Error is not recoverable")
            result.final_error = "Error marked as non-recoverable"
            return result

        # Determine recovery strategy based on error type
        strategies = self._determine_strategies(error, context)

        for attempt_num, strategy in enumerate(strategies, 1):
            if attempt_num > self.max_retries:
                break

            attempt = RecoveryAttempt(
                strategy=strategy,
                attempt_number=attempt_num,
            )

            start_time = datetime.now(timezone.utc)

            try:
                success = await self._execute_strategy(
                    strategy, error, context, attempt_num
                )
                attempt.success = success
                attempt.duration_seconds = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

                if success:
                    result.recovered = True
                    result.strategy_used = strategy
                    result.attempts.append(attempt)
                    logger.info(
                        "Recovery successful",
                        strategy=strategy.value,
                        attempt=attempt_num,
                    )
                    break
                else:
                    attempt.error = f"Strategy {strategy.value} failed"
                    result.attempts.append(attempt)
                    logger.warning(
                        "Recovery attempt failed",
                        strategy=strategy.value,
                        attempt=attempt_num,
                    )

            except Exception as e:
                attempt.error = str(e)
                attempt.duration_seconds = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()
                result.attempts.append(attempt)
                logger.error(
                    "Recovery attempt raised exception",
                    strategy=strategy.value,
                    error=str(e),
                )

            # Wait before next attempt
            if attempt_num < len(strategies):
                await asyncio.sleep(self.retry_delay)

        if not result.recovered:
            result.final_error = "All recovery strategies exhausted"
            logger.error("Recovery failed after all attempts")

        self._recovery_history.append(result)
        return result

    def _determine_strategies(
        self, error: CoraxError, context: Dict[str, Any]
    ) -> List[RecoveryStrategy]:
        """Determine appropriate recovery strategies for the error."""
        strategies = []

        from src.core.exceptions import (
            InstallationError,
            PermissionError,
            ConfigurationError,
            DetectionError,
        )

        if isinstance(error, InstallationError):
            strategies = [
                RecoveryStrategy.RETRY,
                RecoveryStrategy.CLEAN_CACHE,
                RecoveryStrategy.REINSTALL,
            ]
        elif isinstance(error, PermissionError):
            strategies = [
                RecoveryStrategy.ESCALATE_PRIVILEGES,
                RecoveryStrategy.RETRY,
            ]
        elif isinstance(error, ConfigurationError):
            strategies = [
                RecoveryStrategy.RETRY,
                RecoveryStrategy.CLEAN_CACHE,
            ]
        elif isinstance(error, DetectionError):
            strategies = [
                RecoveryStrategy.RETRY,
                RecoveryStrategy.SKIP,
            ]
        else:
            strategies = [RecoveryStrategy.RETRY, RecoveryStrategy.SKIP]

        return strategies

    async def _execute_strategy(
        self,
        strategy: RecoveryStrategy,
        error: CoraxError,
        context: Dict[str, Any],
        attempt_num: int,
    ) -> bool:
        """Execute a specific recovery strategy."""
        # Check for custom handler first
        if strategy.value in self._custom_handlers:
            handler = self._custom_handlers[strategy.value]
            return await handler(error=error, context=context, attempt=attempt_num)

        if strategy == RecoveryStrategy.RETRY:
            logger.info("Retrying operation", attempt=attempt_num)
            return True  # Signal to retry

        elif strategy == RecoveryStrategy.CLEAN_CACHE:
            logger.info("Cleaning cache")
            # TODO: Implement cache cleaning
            await asyncio.sleep(1)
            return True

        elif strategy == RecoveryStrategy.REINSTALL:
            logger.info("Would reinstall tool")
            # TODO: Implement reinstallation
            return False

        elif strategy == RecoveryStrategy.ESCALATE_PRIVILEGES:
            logger.info("Would escalate privileges")
            # TODO: Implement privilege escalation
            return False

        elif strategy == RecoveryStrategy.SKIP:
            logger.info("Skipping operation")
            return True

        return False

    def register_handler(
        self,
        strategy: RecoveryStrategy,
        handler: Callable[..., Awaitable[bool]],
    ) -> None:
        """
        Register a custom recovery handler.

        Args:
            strategy: The strategy to handle
            handler: Async function that takes error, context, attempt
        """
        self._custom_handlers[strategy.value] = handler
        logger.debug("Registered custom handler", strategy=strategy.value)

    async def check_health(self, component: str) -> HealthStatus:
        """
        Check the health of a component.

        Args:
            component: Component name to check

        Returns:
            HealthStatus for the component
        """
        status = self._health_status.get(
            component,
            HealthStatus(),
        )
        status.last_check = datetime.now(timezone.utc).isoformat()
        self._health_status[component] = status
        return status

    async def start_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._monitoring_task:
            return

        async def monitor_loop():
            while True:
                for component in list(self._health_status.keys()):
                    await self.check_health(component)
                await asyncio.sleep(self.health_check_interval)

        self._monitoring_task = asyncio.create_task(monitor_loop())
        logger.info("Health monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None
            logger.info("Health monitoring stopped")

    def get_recovery_history(self) -> List[RecoveryResult]:
        """Get the history of all recovery attempts."""
        return list(self._recovery_history)

    def get_health_status(self) -> Dict[str, HealthStatus]:
        """Get the health status of all components."""
        return dict(self._health_status)
