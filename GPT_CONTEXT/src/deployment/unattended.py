"""
Corax Orchestrator - Unattended Deployment Mode.

Provides overnight/silent deployment support with automatic
continuation, reboot recovery, checkpoint persistence, queued
retry handling, and automatic recovery flows.

Prevents:
- Blocked subprocesses (timeout enforcement)
- Infinite retries (bounded exhaustion)
- Hanging prompts (non-interactive flags)
- Stalled deployments (watchdog timer)
"""

from typing import Dict, Any, List, Optional, Set, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import json
import os
import time
from pathlib import Path

from src.core.logging import get_logger
from src.deployment.execution.executor import DeploymentExecutor, ToolDeploymentResult
from src.deployment.execution.session import DeploymentSession, DeploymentSessionResult
from src.deployment.operations import OperationTracker, OperationType, OperationStatus
from src.deployment.installers.base import AIInstallerBase, InstallStatus

logger = get_logger(__name__)


@dataclass
class UnattendedConfig:
    """Configuration for unattended deployment mode."""
    max_retry_rounds: int = 3
    retry_backoff_seconds: int = 5
    watchdog_timeout_minutes: int = 30
    checkpoint_interval_seconds: int = 60
    max_consecutive_failures: int = 5
    reboot_detection_retries: int = 3
    reboot_detection_delay: int = 10
    auto_continue_after_reboot: bool = True
    generate_report: bool = True
    save_checkpoints: bool = True


@dataclass
class UnattendedResult:
    """Result of an unattended deployment run."""
    success: bool = False
    session_result: Optional[DeploymentSessionResult] = None
    checkpoints_saved: int = 0
    retry_rounds_completed: int = 0
    watchdog_triggered: bool = False
    reboot_detected: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    checkpoint_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "session_result": self.session_result.to_dict() if self.session_result else None,
            "checkpoints_saved": self.checkpoints_saved,
            "retry_rounds_completed": self.retry_rounds_completed,
            "watchdog_triggered": self.watchdog_triggered,
            "reboot_detected": self.reboot_detected,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_seconds": round(self.duration_seconds, 1),
            "checkpoint_paths": self.checkpoint_paths,
        }


class UnattendedDeployment:
    """
    Unattended deployment mode for overnight/silent execution.

    Features:
    - Watchdog timer to detect stalled deployments
    - Automatic retry with bounded exhaustion
    - Checkpoint persistence for reboot recovery
    - Reboot detection and automatic continuation
    - Non-interactive flag enforcement
    - Comprehensive diagnostics and reporting

    Usage:
        config = UnattendedConfig(watchdog_timeout_minutes=30)
        unattended = UnattendedDeployment(config)
        result = await unattended.run(tool_keys=["ollama", "open_webui"])
    """

    def __init__(
        self,
        config: Optional[UnattendedConfig] = None,
        session: Optional[DeploymentSession] = None,
        data_dir: str = "data",
    ) -> None:
        self._config = config or UnattendedConfig()
        self._session = session or DeploymentSession(data_dir=data_dir)
        self._data_dir = data_dir
        self._watchdog_task: Optional[asyncio.Task] = None
        self._last_activity_time: float = time.time()
        self._checkpoint_count: int = 0
        self._consecutive_failures: int = 0
        self._cancelled: bool = False

    @property
    def session(self) -> DeploymentSession:
        return self._session

    @property
    def executor(self) -> DeploymentExecutor:
        return self._session.executor

    async def run(
        self,
        tool_keys: List[str],
        profile_name: str = "unattended",
        skip_existing: bool = True,
        parallel: bool = False,
    ) -> UnattendedResult:
        """
        Run unattended deployment with full lifecycle management.

        Args:
            tool_keys: List of tool keys to deploy
            profile_name: Profile name for reporting
            skip_existing: Skip already-installed tools
            parallel: Run independent tools in parallel

        Returns:
            UnattendedResult with complete deployment results
        """
        result = UnattendedResult()
        start_time = time.time()

        logger.info(
            "Starting unattended deployment",
            tools=tool_keys,
            profile=profile_name,
            watchdog_minutes=self._config.watchdog_timeout_minutes,
        )

        try:
            # Start watchdog
            self._start_watchdog()

            # Start session
            self._session.start_session(profile_name=profile_name)

            # Phase 1: Check for reboot continuation
            if self._config.auto_continue_after_reboot:
                reboot_result = await self._check_reboot_continuation()
                if reboot_result:
                    result.reboot_detected = True
                    logger.info("Detected reboot continuation, resuming deployment")
                    # Merge reboot results
                    if reboot_result.session_result:
                        result.session_result = reboot_result.session_result
                    return reboot_result

            # Phase 2: Execute deployment
            session_result = await self._session.deploy_tools(
                tool_keys=tool_keys,
                skip_existing=skip_existing,
                parallel=parallel,
            )
            result.session_result = session_result

            # Phase 3: Process retry queue with bounded rounds
            retry_result = await self._process_retry_queue_bounded()
            result.retry_rounds_completed = retry_result

            # Phase 4: Save final checkpoint
            if self._config.save_checkpoints:
                checkpoint_path = await self._save_checkpoint(
                    tool_keys, session_result
                )
                if checkpoint_path:
                    result.checkpoint_paths.append(checkpoint_path)
                    result.checkpoints_saved += 1

            # Determine overall success
            if session_result.status == "completed":
                result.success = True
            elif session_result.status == "partial":
                result.success = True  # Partial success is acceptable
                result.warnings.append(
                    f"Partial deployment: {len(session_result.tools_failed)} tools failed"
                )
            else:
                result.success = False
                result.errors.append(
                    f"Deployment failed: {session_result.status}"
                )

        except asyncio.CancelledError:
            result.warnings.append("Deployment was cancelled")
            result.success = False
        except Exception as e:
            error_msg = f"Unattended deployment error: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            result.success = False
        finally:
            # Stop watchdog
            self._stop_watchdog()
            result.duration_seconds = time.time() - start_time

        return result

    async def _process_retry_queue_bounded(self) -> int:
        """
        Process retry queue with bounded rounds and backoff.

        Returns:
            Number of retry rounds completed
        """
        rounds_completed = 0

        for round_num in range(self._config.max_retry_rounds):
            if self._cancelled:
                break

            retry_queue = self._session.executor.retry_queue
            if not retry_queue.has_pending():
                break

            logger.info(
                f"Retry round {round_num + 1}/{self._config.max_retry_rounds}",
                pending=retry_queue.get_summary().get("pending_retries", 0),
            )

            # Wait for backoff timers
            await asyncio.sleep(self._config.retry_backoff_seconds)

            # Process due retries
            await self._session.executor._process_retry_queue()
            rounds_completed += 1

            # Check for consecutive failure threshold
            if self._consecutive_failures >= self._config.max_consecutive_failures:
                logger.warning(
                    "Too many consecutive failures, stopping retry",
                    failures=self._consecutive_failures,
                )
                break

        return rounds_completed

    async def _check_reboot_continuation(self) -> Optional[UnattendedResult]:
        """
        Check if we need to continue after a reboot.

        Looks for saved checkpoint files and resumes if found.
        """
        checkpoint_dir = os.path.join(self._data_dir, "persistence")
        if not os.path.exists(checkpoint_dir):
            return None

        # Find latest checkpoint
        checkpoints = [
            f for f in os.listdir(checkpoint_dir)
            if f.startswith("checkpoint_") and f.endswith(".json")
        ]
        if not checkpoints:
            return None

        # Sort by modification time (newest first)
        checkpoints.sort(
            key=lambda f: os.path.getmtime(os.path.join(checkpoint_dir, f)),
            reverse=True,
        )

        latest = checkpoints[0]
        checkpoint_path = os.path.join(checkpoint_dir, latest)

        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Check if this checkpoint is stale (> 1 hour old)
            checkpoint_time = os.path.getmtime(checkpoint_path)
            if time.time() - checkpoint_time > 3600:
                logger.info("Checkpoint is too old, starting fresh")
                return None

            tool_keys = state.get("tool_keys", [])
            if not tool_keys:
                return None

            logger.info(
                "Resuming from checkpoint",
                checkpoint=latest,
                tools=tool_keys,
            )

            # Resume session
            session_id = state.get("session_id")
            if session_id:
                session_result = await self._session.resume_session(session_id)
                if session_result:
                    result = UnattendedResult(
                        success=session_result.status != "failed",
                        session_result=session_result,
                        reboot_detected=True,
                    )
                    return result

        except Exception as e:
            logger.warning("Failed to resume from checkpoint", error=str(e))

        return None

    async def _save_checkpoint(
        self,
        tool_keys: List[str],
        session_result: DeploymentSessionResult,
    ) -> Optional[str]:
        """Save a deployment checkpoint for reboot recovery."""
        checkpoint_dir = os.path.join(self._data_dir, "persistence")
        os.makedirs(checkpoint_dir, exist_ok=True)

        checkpoint_path = os.path.join(
            checkpoint_dir,
            f"checkpoint_{self._checkpoint_count:04d}.json",
        )

        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_result.session_id,
            "tool_keys": tool_keys,
            "tools_installed": session_result.tools_installed,
            "tools_failed": session_result.tools_failed,
            "tools_skipped": session_result.tools_skipped,
            "status": session_result.status,
            "profile_name": session_result.profile_name,
        }

        try:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            self._checkpoint_count += 1
            logger.info("Checkpoint saved", path=checkpoint_path)
            return checkpoint_path
        except Exception as e:
            logger.warning("Failed to save checkpoint", error=str(e))
            return None

    def _start_watchdog(self) -> None:
        """Start the watchdog timer to detect stalled deployments."""
        self._last_activity_time = time.time()

        async def watchdog_loop():
            while not self._cancelled:
                await asyncio.sleep(30)  # Check every 30 seconds
                elapsed = time.time() - self._last_activity_time
                timeout_seconds = self._config.watchdog_timeout_minutes * 60

                if elapsed > timeout_seconds:
                    logger.warning(
                        "Watchdog timeout triggered",
                        elapsed_minutes=round(elapsed / 60, 1),
                        timeout_minutes=self._config.watchdog_timeout_minutes,
                    )
                    # Cancel the deployment
                    self._session.executor.cancel()
                    break

        self._watchdog_task = asyncio.create_task(watchdog_loop())

    def _stop_watchdog(self) -> None:
        """Stop the watchdog timer."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None

    def _update_activity(self) -> None:
        """Update the last activity timestamp."""
        self._last_activity_time = time.time()

    def cancel(self) -> None:
        """Cancel the unattended deployment."""
        self._cancelled = True
        self._session.executor.cancel()
        logger.info("Unattended deployment cancelled")

    async def run_with_reboot_handling(
        self,
        tool_keys: List[str],
        profile_name: str = "unattended",
        max_reboot_retries: int = 3,
    ) -> UnattendedResult:
        """
        Run deployment with automatic reboot handling.

        If a reboot is detected, waits for the system to come back
        and continues the deployment automatically.

        Args:
            tool_keys: List of tool keys to deploy
            profile_name: Profile name for reporting
            max_reboot_retries: Maximum number of reboot retries

        Returns:
            UnattendedResult with complete deployment results
        """
        for attempt in range(max_reboot_retries):
            result = await self.run(
                tool_keys=tool_keys,
                profile_name=profile_name,
            )

            if result.success:
                return result

            # Check if reboot is needed
            if self._is_reboot_needed(result):
                logger.info(
                    "Reboot needed, will continue after restart",
                    attempt=attempt + 1,
                )
                # Save final checkpoint before reboot
                if self._config.save_checkpoints:
                    await self._save_checkpoint(
                        tool_keys,
                        result.session_result,
                    )
                # Signal that reboot is needed
                result.warnings.append(
                    "System reboot required to continue deployment"
                )
                return result

            # Non-reboot failure - retry
            if attempt < max_reboot_retries - 1:
                logger.info(
                    "Retrying deployment after failure",
                    attempt=attempt + 1,
                )
                await asyncio.sleep(self._config.reboot_detection_delay)

        return result

    def _is_reboot_needed(self, result: UnattendedResult) -> bool:
        """Check if a reboot is needed based on deployment results."""
        if not result.session_result:
            return False

        # Check for tools that need reboot to complete installation
        for tool_key in result.session_result.tools_failed:
            installer = self._session.executor._installers.get(tool_key)
            if installer:
                # Some installers require reboot (e.g., Python, Node.js)
                if hasattr(installer, "requires_reboot") and installer.requires_reboot:
                    return True

        return False
