"""
Corax Orchestrator — Deployment Recovery Manager Module.

Provides automated recovery from deployment failures:
- Safe-mode fallback for failed operations
- Step-level retry with exponential backoff
- Checkpoint-based recovery for long-running deployments
- Rollback support for partially completed deployments
- Graceful degradation of non-critical features
"""

from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
import os
import pickle
import time
import traceback

from src.core.logging import get_logger

logger = get_logger(__name__)

# Type alias for a deployment step function
DeploymentStep = Callable[..., Dict[str, Any]]


class RecoveryStrategy:
    """Enum-like class for recovery strategies."""
    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    SAFE_MODE_FALLBACK = "safe_mode_fallback"
    SKIP_STEP = "skip_step"
    ROLLBACK = "rollback"
    PROMPT_USER = "prompt_user"
    USE_DEFAULT = "use_default"
    USE_CACHED = "use_cached"


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    success: bool = False
    strategy: str = ""
    step_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fallback_used: bool = False
    duration_ms: float = 0.0
    checkpoint_restored: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "strategy": self.strategy,
            "step_name": self.step_name,
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
            "fallback_used": self.fallback_used,
            "duration_ms": round(self.duration_ms, 2),
            "checkpoint_restored": self.checkpoint_restored,
        }


class DeploymentRecoveryManager:
    """
    Manages deployment recovery with multiple strategies.

    Provides:
    - Retry with configurable attempts, delay, and backoff
    - Safe-mode fallback (disable non-critical features)
    - Checkpoint-based recovery (resume from last successful step)
    - Full rollback of all completed steps
    - Graceful degradation of features
    """

    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 2.0  # seconds
    DEFAULT_BACKOFF_FACTOR = 2.0
    CHECKPOINT_DIR = "checkpoints"

    def __init__(self, checkpoint_dir: Optional[str] = None):
        self._checkpoint_dir = checkpoint_dir or os.path.join(
            os.getcwd(), self.CHECKPOINT_DIR
        )
        os.makedirs(self._checkpoint_dir, exist_ok=True)

        self._step_results: Dict[str, Dict[str, Any]] = {}
        self._deployment_id: Optional[str] = None
        self._completed_steps: List[str] = []
        self._failed_steps: List[str] = []
        self._safe_mode: bool = False
        self._safe_mode_features: Dict[str, bool] = {}
        self._rollback_actions: List[Dict[str, Any]] = []

    def initialize_deployment(
        self, deployment_id: Optional[str] = None
    ) -> str:
        """Initialize a new deployment tracking session."""
        self._deployment_id = deployment_id or (
            f"deploy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        )
        self._completed_steps = []
        self._failed_steps = []
        self._step_results = {}
        self._safe_mode = False
        self._rollback_actions = []

        logger.info(
            f"Deployment initialized",
            deployment_id=self._deployment_id,
        )

        return self._deployment_id

    def execute_step(
        self,
        step_name: str,
        step_fn: DeploymentStep,
        *args,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        critical: bool = True,
        safe_mode_fallback: Optional[DeploymentStep] = None,
        rollback_fn: Optional[Callable] = None,
        **kwargs,
    ) -> RecoveryResult:
        """
        Execute a deployment step with automatic recovery.

        Args:
            step_name: Name of the deployment step
            step_fn: Function to execute
            max_retries: Maximum retry attempts
            retry_delay: Initial delay between retries (seconds)
            backoff_factor: Multiply delay by this factor each retry
            critical: If True, failure prevents further deployment
            safe_mode_fallback: Alternative function for safe mode
            rollback_fn: Function to undo this step if rollback needed

        Returns:
            RecoveryResult with execution outcome
        """
        start = time.time()
        result = RecoveryResult(
            step_name=step_name,
        )

        # Check if this step was already completed (from checkpoint)
        if self._is_step_completed(step_name):
            logger.info(f"Step '{step_name}' already completed (from checkpoint)")
            result.success = True
            result.details = {"from_checkpoint": True}
            result.strategy = "checkpoint_restore"
            result.checkpoint_restored = step_name
            result.duration_ms = (time.time() - start) * 1000
            return result

        # Determine which function to use (normal or safe mode fallback)
        if self._safe_mode and safe_mode_fallback:
            actual_fn = safe_mode_fallback
            result.fallback_used = True
            logger.info(
                f"Using safe-mode fallback for step '{step_name}'"
            )
        else:
            actual_fn = step_fn

        # Attempt execution with retries
        attempt = 0
        last_error = None
        current_delay = retry_delay

        while attempt < max_retries:
            attempt += 1
            try:
                logger.info(
                    f"Executing step '{step_name}' (attempt {attempt}/{max_retries})"
                )

                step_result = actual_fn(*args, **kwargs)

                # Record success
                self._completed_steps.append(step_name)
                self._step_results[step_name] = {
                    "success": True,
                    "attempts": attempt,
                    "result": self._serialize_result(step_result),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                # Save checkpoint
                self._save_checkpoint()

                # Register rollback if provided
                if rollback_fn:
                    self._rollback_actions.append({
                        "step": step_name,
                        "rollback_fn": rollback_fn,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                result.success = True
                result.strategy = (
                    "retry" if attempt > 1 else "direct"
                )
                result.details = {
                    "attempts": attempt,
                    "step_result": self._serialize_result(step_result),
                }
                result.duration_ms = (time.time() - start) * 1000

                logger.info(
                    f"Step '{step_name}' completed successfully "
                    f"(attempt {attempt})"
                )
                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Step '{step_name}' failed on attempt {attempt}: {e}",
                    attempt=attempt,
                    max_retries=max_retries,
                )

                if attempt < max_retries:
                    # Exponential backoff
                    sleep_time = current_delay
                    time.sleep(sleep_time)
                    current_delay *= backoff_factor

        # All retries exhausted
        self._failed_steps.append(step_name)
        self._step_results[step_name] = {
            "success": False,
            "attempts": attempt,
            "error": str(last_error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        error_msg = (
            f"Step '{step_name}' failed after {max_retries} attempts: {last_error}"
        )
        result.errors = [error_msg]
        result.strategy = "retry_exhausted"
        result.duration_ms = (time.time() - start) * 1000

        if critical:
            logger.error(error_msg)
            # Auto-enter safe mode on critical failure
            self._safe_mode = True
            result.details = {
                "safe_mode_activated": True,
                "attempts": attempt,
                "last_error": str(last_error),
                "traceback": traceback.format_exc(),
            }
        else:
            logger.warning(f"Non-critical step failed: {error_msg}")
            result.details = {
                "safe_mode_activated": False,
                "attempts": attempt,
                "last_error": str(last_error),
            }

        return result

    def _is_step_completed(self, step_name: str) -> bool:
        """Check if a step is already marked as completed."""
        return step_name in self._completed_steps

    def _serialize_result(self, result: Any) -> Any:
        """Serialize a step result for storage."""
        if hasattr(result, "to_dict"):
            return result.to_dict()
        elif isinstance(result, dict):
            return {
                k: self._serialize_result(v) for k, v in result.items()
            }
        elif isinstance(result, list):
            return [self._serialize_result(v) for v in result]
        else:
            return str(result)

    def execute_chain(
        self,
        steps: List[Tuple[str, DeploymentStep, Dict[str, Any]]],
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        stop_on_failure: bool = True,
    ) -> List[RecoveryResult]:
        """
        Execute a chain of deployment steps in sequence.

        Args:
            steps: List of (step_name, step_fn, kwargs) tuples
            max_retries: Maximum retry attempts per step
            retry_delay: Initial delay between retries
            stop_on_failure: If True, stop chain on first failure

        Returns:
            List of RecoveryResult for each step
        """
        results = []
        for step_name, step_fn, kwargs in steps:
            result = self.execute_step(
                step_name=step_name,
                step_fn=step_fn,
                max_retries=max_retries,
                retry_delay=retry_delay,
                critical=stop_on_failure,
                **kwargs,
            )
            results.append(result)

            if not result.success and stop_on_failure:
                logger.warning(
                    f"Stopping deployment chain at step '{step_name}' "
                    f"due to failure"
                )
                break

        return results

    def enter_safe_mode(self, reason: str = "") -> None:
        """
        Enter safe mode — use fallbacks for non-critical operations.

        Safe mode disables non-essential features and uses simpler
        (but more reliable) implementations where possible.
        """
        self._safe_mode = True
        logger.warning(f"Entering safe mode: {reason}")

        # Default safe mode feature flags
        self._safe_mode_features = {
            "gpu_acceleration": False,
            "network_heavy_operations": False,
            "concurrent_execution": False,
            "detailed_logging": True,
            "health_checks": True,
            "progress_reporting": True,
        }

    def exit_safe_mode(self) -> None:
        """Exit safe mode and restore normal operations."""
        self._safe_mode = False
        self._safe_mode_features = {}
        logger.info("Exiting safe mode")

    def is_safe_mode(self) -> bool:
        """Check if the deployment is in safe mode."""
        return self._safe_mode

    def get_safe_mode_feature(self, feature: str, default: bool = True) -> bool:
        """
        Check if a specific feature is enabled in safe mode.

        Args:
            feature: Feature name
            default: Default value if feature not explicitly set

        Returns:
            True if the feature is enabled
        """
        if not self._safe_mode:
            return True
        return self._safe_mode_features.get(feature, default)

    def rollback(self, reason: str = "") -> RecoveryResult:
        """
        Roll back all completed deployment steps.

        Executes registered rollback functions in reverse order.
        """
        start = time.time()
        result = RecoveryResult(
            strategy=RecoveryStrategy.ROLLBACK,
            step_name="full_rollback",
        )

        rollback_count = 0
        errors = []

        for action in reversed(self._rollback_actions):
            step_name = action["step"]
            rollback_fn = action["rollback_fn"]

            try:
                logger.info(f"Rolling back step '{step_name}'...")
                rollback_fn()
                rollback_count += 1

                # Remove from completed steps
                if step_name in self._completed_steps:
                    self._completed_steps.remove(step_name)

                logger.info(f"Rollback of '{step_name}' completed")

            except Exception as e:
                error_msg = f"Rollback of '{step_name}' failed: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

        # Clear deployment state
        self._safe_mode = False
        self._safe_mode_features = {}

        result.success = len(errors) == 0
        result.details = {
            "steps_rolled_back": rollback_count,
            "total_rollback_actions": len(self._rollback_actions),
            "reason": reason,
        }
        result.errors = errors
        result.duration_ms = (time.time() - start) * 1000

        if rollback_count > 0:
            logger.info(
                f"Rollback completed: {rollback_count} steps undone",
                reason=reason,
            )

        return result

    def get_deployment_status(self) -> Dict[str, Any]:
        """Get the current deployment status."""
        return {
            "deployment_id": self._deployment_id,
            "safe_mode": self._safe_mode,
            "completed_steps": list(self._completed_steps),
            "failed_steps": list(self._failed_steps),
            "total_steps": (
                len(self._completed_steps) + len(self._failed_steps)
            ),
            "rollback_actions_count": len(self._rollback_actions),
            "safe_mode_features": dict(self._safe_mode_features),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Checkpoint Management
    # ------------------------------------------------------------------

    def _save_checkpoint(self) -> None:
        """Save a deployment checkpoint to disk."""
        if not self._deployment_id:
            return

        checkpoint = {
            "deployment_id": self._deployment_id,
            "completed_steps": list(self._completed_steps),
            "failed_steps": list(self._failed_steps),
            "step_results": self._step_results,
            "safe_mode": self._safe_mode,
            "safe_mode_features": dict(self._safe_mode_features),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        checkpoint_path = os.path.join(
            self._checkpoint_dir,
            f"{self._deployment_id}.ckpt",
        )

        try:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=2, default=str)
            logger.debug(f"Checkpoint saved: {checkpoint_path}")
        except (IOError, OSError) as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    def restore_checkpoint(
        self, deployment_id: Optional[str] = None
    ) -> bool:
        """
        Restore deployment state from a checkpoint.

        Args:
            deployment_id: Deployment ID to restore, or None for latest

        Returns:
            True if checkpoint was restored successfully
        """
        if deployment_id:
            checkpoint_path = os.path.join(
                self._checkpoint_dir,
                f"{deployment_id}.ckpt",
            )
        else:
            # Find latest checkpoint
            checkpoints = sorted(
                [
                    f for f in os.listdir(self._checkpoint_dir)
                    if f.endswith(".ckpt")
                ],
                reverse=True,
            )
            if not checkpoints:
                logger.info("No checkpoints found to restore")
                return False
            checkpoint_path = os.path.join(
                self._checkpoint_dir, checkpoints[0]
            )

        if not os.path.isfile(checkpoint_path):
            logger.warning(f"Checkpoint not found: {checkpoint_path}")
            return False

        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)

            self._deployment_id = checkpoint["deployment_id"]
            self._completed_steps = list(checkpoint["completed_steps"])
            self._failed_steps = list(checkpoint["failed_steps"])
            self._step_results = checkpoint["step_results"]
            self._safe_mode = checkpoint.get("safe_mode", False)
            self._safe_mode_features = checkpoint.get(
                "safe_mode_features", {}
            )

            logger.info(
                f"Checkpoint restored: {checkpoint_path}",
                completed_steps=len(self._completed_steps),
                failed_steps=len(self._failed_steps),
            )
            return True

        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            return False

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all available deployment checkpoints."""
        checkpoints = []
        for filename in sorted(
            os.listdir(self._checkpoint_dir),
            reverse=True,
        ):
            if not filename.endswith(".ckpt"):
                continue

            filepath = os.path.join(self._checkpoint_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                checkpoints.append({
                    "filename": filename,
                    "deployment_id": data.get("deployment_id", "unknown"),
                    "completed_steps": len(data.get("completed_steps", [])),
                    "failed_steps": len(data.get("failed_steps", [])),
                    "safe_mode": data.get("safe_mode", False),
                    "timestamp": data.get("timestamp", "unknown"),
                    "size_bytes": os.path.getsize(filepath),
                })
            except (json.JSONDecodeError, IOError) as e:
                checkpoints.append({
                    "filename": filename,
                    "error": str(e),
                })

        return checkpoints

    def clean_old_checkpoints(
        self, max_age_days: int = 7
    ) -> int:
        """Remove checkpoints older than max_age_days."""
        count = 0
        cutoff = datetime.now(timezone.utc).timestamp() - (
            max_age_days * 86400
        )

        for filename in os.listdir(self._checkpoint_dir):
            if not filename.endswith(".ckpt"):
                continue

            filepath = os.path.join(self._checkpoint_dir, filename)
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    count += 1
            except OSError as e:
                logger.debug(
                    f"Failed to clean checkpoint {filename}: {e}"
                )

        return count
