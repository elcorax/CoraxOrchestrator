"""
Corax Orchestrator - Execution Recovery Capability.

Provides recovery integration for the execution layer. Supports
checkpoint creation, command recovery strategies, and integration
with the self-healing engine for automatic failure recovery.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import asyncio
import json
import os
import time
from uuid import uuid4

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class CommandRecoveryStrategy(Enum):
    """Strategies for recovering from command failures."""
    RETRY = "retry"
    RETRY_BACKOFF = "retry_backoff"
    ALTERNATIVE_COMMAND = "alternative_command"
    SKIP = "skip"
    ABORT = "abort"
    FALLBACK = "fallback"


@dataclass
class ExecutionCheckpoint:
    """
    A checkpoint in the execution flow.

    Captures the state at a point in execution so the agent
    can resume from that point if a failure occurs.
    """
    checkpoint_id: str
    step_name: str
    step_number: int
    state: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "step_name": self.step_name,
            "step_number": self.step_number,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class RecoveryAction:
    """
    A recovery action to take when a failure occurs.

    Defines what to do when a command or operation fails,
    including retry logic, alternative approaches, and
    fallback strategies.
    """
    action_id: str
    strategy: CommandRecoveryStrategy
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    alternative_command: Optional[str] = None
    fallback_action: Optional[str] = None
    condition: Optional[str] = None  # Python expression to evaluate
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExecutionRecoveryCapability(CapabilityBase):
    """
    Execution recovery capability.

    Provides:
    - Checkpoint creation and management
    - Command recovery strategies (retry, backoff, alternative)
    - Integration with self-healing engine
    - Failure analysis and recovery planning
    - Checkpoint-based execution resumption
    """

    def __init__(self) -> None:
        super().__init__()
        self._checkpoints: Dict[str, ExecutionCheckpoint] = {}
        self._recovery_actions: Dict[str, RecoveryAction] = {}
        self._checkpoint_dir: Optional[Path] = None
        self._recovery_callbacks: List[Callable] = []

    @property
    def name(self) -> str:
        return "execution_recovery"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Execution recovery providing checkpoint management, "
            "command recovery strategies, and integration with the "
            "self-healing engine for automatic failure recovery."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the recovery capability."""
        self._context = context
        self._checkpoint_dir = Path("data/persistence/checkpoints")
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info("Execution recovery capability initialized")

    async def shutdown(self) -> None:
        """Shutdown the recovery capability."""
        self._initialized = False
        logger.info("Execution recovery capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check recovery capability health."""
        return {
            "healthy": self._initialized,
            "active_checkpoints": len(self._checkpoints),
            "recovery_actions": len(self._recovery_actions),
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List recovery operations."""
        return [
            {
                "name": "create_checkpoint",
                "description": "Create an execution checkpoint",
                "parameters": ["step_name", "step_number", "state"],
            },
            {
                "name": "restore_checkpoint",
                "description": "Restore state from a checkpoint",
                "parameters": ["checkpoint_id"],
            },
            {
                "name": "list_checkpoints",
                "description": "List all checkpoints",
                "parameters": [],
            },
            {
                "name": "get_latest_checkpoint",
                "description": "Get the most recent checkpoint",
                "parameters": [],
            },
            {
                "name": "register_recovery_action",
                "description": "Register a recovery action for failures",
                "parameters": ["action_id", "strategy", "max_retries"],
            },
            {
                "name": "execute_recovery",
                "description": "Execute recovery for a failed operation",
                "parameters": ["action_id", "failure_info"],
            },
            {
                "name": "analyze_failure",
                "description": "Analyze a failure and suggest recovery",
                "parameters": ["failure_info"],
            },
            {
                "name": "clear_checkpoints",
                "description": "Clear all checkpoints",
                "parameters": [],
            },
        ]

    # --- Checkpoint Management ---

    async def create_checkpoint(
        self,
        step_name: str,
        step_number: int,
        state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CapabilityResult:
        """
        Create an execution checkpoint.

        Args:
            step_name: Name of the step being checkpointed
            step_number: Step number in the execution flow
            state: State data to capture
            metadata: Additional metadata

        Returns:
            CapabilityResult with checkpoint information
        """
        if not self._initialized:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Recovery capability not initialized",
            )

        checkpoint = ExecutionCheckpoint(
            checkpoint_id=f"ckpt_{uuid4().hex[:8]}",
            step_name=step_name,
            step_number=step_number,
            state=state or {},
            metadata=metadata or {},
        )

        self._checkpoints[checkpoint.checkpoint_id] = checkpoint

        # Persist checkpoint
        await self._persist_checkpoint(checkpoint)

        logger.info(
            "Checkpoint created",
            checkpoint_id=checkpoint.checkpoint_id,
            step=step_name,
            number=step_number,
        )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data=checkpoint.to_dict(),
        )

    async def restore_checkpoint(self, checkpoint_id: str) -> CapabilityResult:
        """
        Restore state from a checkpoint.

        Args:
            checkpoint_id: The checkpoint to restore

        Returns:
            CapabilityResult with restored state
        """
        checkpoint = self._checkpoints.get(checkpoint_id)
        if not checkpoint:
            # Try to load from disk
            checkpoint = await self._load_checkpoint(checkpoint_id)
            if not checkpoint:
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=f"Checkpoint '{checkpoint_id}' not found",
                )

        logger.info(
            "Checkpoint restored",
            checkpoint_id=checkpoint_id,
            step=checkpoint.step_name,
        )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={
                "checkpoint": checkpoint.to_dict(),
                "state": checkpoint.state,
            },
        )

    async def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints."""
        # Also load persisted checkpoints
        await self._load_persisted_checkpoints()

        return [
            ckpt.to_dict() for ckpt in sorted(
                self._checkpoints.values(),
                key=lambda c: c.step_number,
            )
        ]

    async def get_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Get the most recent checkpoint."""
        if not self._checkpoints:
            await self._load_persisted_checkpoints()

        if not self._checkpoints:
            return None

        latest = max(
            self._checkpoints.values(),
            key=lambda c: c.step_number,
        )
        return latest.to_dict()

    async def clear_checkpoints(self) -> CapabilityResult:
        """
        Clear all checkpoints.

        Returns:
            CapabilityResult
        """
        self._checkpoints.clear()

        # Clear persisted checkpoints
        if self._checkpoint_dir:
            for f in self._checkpoint_dir.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass

        logger.info("All checkpoints cleared")

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={"message": "All checkpoints cleared"},
        )

    # --- Recovery Actions ---

    async def register_recovery_action(
        self,
        action_id: str,
        strategy: CommandRecoveryStrategy = CommandRecoveryStrategy.RETRY_BACKOFF,
        max_retries: int = 3,
        alternative_command: Optional[str] = None,
        fallback_action: Optional[str] = None,
    ) -> CapabilityResult:
        """
        Register a recovery action for command failures.

        Args:
            action_id: Unique identifier for this action
            strategy: Recovery strategy to use
            max_retries: Maximum number of retries
            alternative_command: Alternative command for ALTERNATIVE_COMMAND strategy
            fallback_action: Fallback action for FALLBACK strategy

        Returns:
            CapabilityResult
        """
        action = RecoveryAction(
            action_id=action_id,
            strategy=strategy,
            max_retries=max_retries,
            alternative_command=alternative_command,
            fallback_action=fallback_action,
        )

        self._recovery_actions[action_id] = action

        logger.info(
            "Recovery action registered",
            action_id=action_id,
            strategy=strategy.value,
        )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={
                "action_id": action_id,
                "strategy": strategy.value,
                "max_retries": max_retries,
            },
        )

    async def execute_recovery(
        self,
        action_id: str,
        failure_info: Dict[str, Any],
    ) -> CapabilityResult:
        """
        Execute recovery for a failed operation.

        Args:
            action_id: The recovery action to execute
            failure_info: Information about the failure

        Returns:
            CapabilityResult with recovery result
        """
        action = self._recovery_actions.get(action_id)
        if not action:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Recovery action '{action_id}' not found",
            )

        logger.info(
            "Executing recovery",
            action_id=action_id,
            strategy=action.strategy.value,
            failure=failure_info.get("error", "unknown"),
        )

        # Notify recovery callbacks
        self._notify_recovery(action, failure_info)

        if action.strategy == CommandRecoveryStrategy.RETRY:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={
                    "strategy": "retry",
                    "max_retries": action.max_retries,
                    "retry_delay": action.retry_delay_seconds,
                },
            )

        elif action.strategy == CommandRecoveryStrategy.RETRY_BACKOFF:
            retry_count = failure_info.get("retry_count", 0)
            delay = action.retry_delay_seconds * (action.backoff_multiplier ** retry_count)

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={
                    "strategy": "retry_backoff",
                    "max_retries": action.max_retries,
                    "retry_delay": delay,
                    "backoff_multiplier": action.backoff_multiplier,
                },
            )

        elif action.strategy == CommandRecoveryStrategy.ALTERNATIVE_COMMAND:
            if action.alternative_command:
                return CapabilityResult(
                    success=True,
                    capability=self.name,
                    data={
                        "strategy": "alternative_command",
                        "alternative_command": action.alternative_command,
                    },
                )
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="No alternative command configured",
            )

        elif action.strategy == CommandRecoveryStrategy.SKIP:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={
                    "strategy": "skip",
                    "message": "Skipping failed operation",
                },
            )

        elif action.strategy == CommandRecoveryStrategy.FALLBACK:
            if action.fallback_action:
                return CapabilityResult(
                    success=True,
                    capability=self.name,
                    data={
                        "strategy": "fallback",
                        "fallback_action": action.fallback_action,
                    },
                )
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="No fallback action configured",
            )

        else:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Unknown recovery strategy: {action.strategy}",
            )

    # --- Failure Analysis ---

    async def analyze_failure(
        self,
        failure_info: Dict[str, Any],
    ) -> CapabilityResult:
        """
        Analyze a failure and suggest recovery strategy.

        Args:
            failure_info: Information about the failure

        Returns:
            CapabilityResult with analysis and suggested recovery
        """
        error = failure_info.get("error", "")
        exit_code = failure_info.get("exit_code")
        command = failure_info.get("command", "")
        retry_count = failure_info.get("retry_count", 0)

        analysis = {
            "error": error,
            "exit_code": exit_code,
            "command": command[:100],
            "retry_count": retry_count,
            "suggested_strategy": CommandRecoveryStrategy.RETRY_BACKOFF.value,
            "analysis": [],
        }

        # Analyze common failure patterns
        if exit_code == 2:
            analysis["analysis"].append("Command not found or invalid arguments")
            analysis["suggested_strategy"] = CommandRecoveryStrategy.ALTERNATIVE_COMMAND.value

        elif exit_code == 1 and "permission" in error.lower():
            analysis["analysis"].append("Permission denied - may need elevation")
            analysis["suggested_strategy"] = CommandRecoveryStrategy.RETRY.value

        elif exit_code == 1 and "timeout" in error.lower():
            analysis["analysis"].append("Operation timed out")
            analysis["suggested_strategy"] = CommandRecoveryStrategy.RETRY_BACKOFF.value

        elif exit_code == 1 and "not found" in error.lower():
            analysis["analysis"].append("Resource not found")
            analysis["suggested_strategy"] = CommandRecoveryStrategy.SKIP.value

        elif retry_count >= 3:
            analysis["analysis"].append("Multiple retries exhausted")
            analysis["suggested_strategy"] = CommandRecoveryStrategy.FALLBACK.value

        else:
            analysis["analysis"].append("Unknown failure - will retry with backoff")

        return CapabilityResult(
            success=True,
            capability=self.name,
            data=analysis,
        )

    # --- Recovery Callbacks ---

    def on_recovery(self, callback: Callable[[RecoveryAction, Dict[str, Any]], None]) -> None:
        """Register a callback for recovery events."""
        self._recovery_callbacks.append(callback)

    # --- Internal Methods ---

    async def _persist_checkpoint(self, checkpoint: ExecutionCheckpoint) -> None:
        """Persist a checkpoint to disk."""
        if not self._checkpoint_dir:
            return

        filepath = self._checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "step_name": checkpoint.step_name,
                    "step_number": checkpoint.step_number,
                    "state": checkpoint.state,
                    "created_at": checkpoint.created_at,
                    "metadata": checkpoint.metadata,
                }, f, indent=2)
        except Exception as e:
            logger.error("Failed to persist checkpoint", error=str(e))

    async def _load_checkpoint(self, checkpoint_id: str) -> Optional[ExecutionCheckpoint]:
        """Load a checkpoint from disk."""
        if not self._checkpoint_dir:
            return None

        filepath = self._checkpoint_dir / f"{checkpoint_id}.json"
        if not filepath.exists():
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            checkpoint = ExecutionCheckpoint(
                checkpoint_id=data["checkpoint_id"],
                step_name=data["step_name"],
                step_number=data["step_number"],
                state=data.get("state", {}),
                created_at=data.get("created_at", ""),
                metadata=data.get("metadata", {}),
            )
            self._checkpoints[checkpoint.checkpoint_id] = checkpoint
            return checkpoint
        except Exception as e:
            logger.error("Failed to load checkpoint", error=str(e))
            return None

    async def _load_persisted_checkpoints(self) -> None:
        """Load all persisted checkpoints from disk."""
        if not self._checkpoint_dir:
            return

        for filepath in self._checkpoint_dir.glob("*.json"):
            checkpoint_id = filepath.stem
            if checkpoint_id not in self._checkpoints:
                await self._load_checkpoint(checkpoint_id)

    def _notify_recovery(
        self,
        action: RecoveryAction,
        failure_info: Dict[str, Any],
    ) -> None:
        """Notify recovery callbacks."""
        for callback in self._recovery_callbacks:
            try:
                callback(action, failure_info)
            except Exception as e:
                logger.error("Recovery callback error", error=str(e))
