"""
Corax Orchestrator - Deployment Executor.

The real execution engine that drives actual installations.
Coordinates terminal sessions, retry queues, failure analysis,
and repair execution for fault-tolerant autonomous deployment.
"""

from typing import Dict, Any, List, Optional, Set, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import time
import os

from src.core.logging import get_logger
from src.deployment.operations import (
    OperationTracker,
    OperationType,
    OperationStatus,
    FailureCategory,
)
from src.deployment.execution.terminal import TerminalSession, TerminalResult
from src.deployment.execution.retry_queue import RetryQueue, RetryEntry
from src.deployment.execution.failure_analyzer import FailureAnalyzer, FailureAnalysis
from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus
from src.deployment.repair.engine import RepairEngine
from src.deployment.validation import EnvironmentValidator, ValidationResult

logger = get_logger(__name__)


@dataclass
class ToolDeploymentResult:
    """Result of deploying a single tool."""
    tool_key: str
    tool_name: str
    status: str  # "installed", "skipped", "failed", "retrying"
    version: Optional[str] = None
    error: Optional[str] = None
    failure_analysis: Optional[FailureAnalysis] = None
    retry_attempts: int = 0
    duration_ms: float = 0.0
    operation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_key": self.tool_key,
            "tool_name": self.tool_name,
            "status": self.status,
            "version": self.version,
            "error": self.error[:500] if self.error else None,
            "failure_analysis": self.failure_analysis.to_dict() if self.failure_analysis else None,
            "retry_attempts": self.retry_attempts,
            "duration_ms": round(self.duration_ms, 1),
            "operation_id": self.operation_id,
        }


class DeploymentExecutor:
    """
    Real execution engine for autonomous deployment.

    This is the core engine that:
    1. Executes real installations via terminal sessions
    2. Handles failures gracefully (continues deployment)
    3. Queues failed operations for deferred retry
    4. Analyzes failures for classification and repair
    5. Executes repair actions automatically
    6. Validates installations after completion
    7. Produces structured execution logs and reports

    The executor NEVER gets stuck permanently on one failed installation.
    It continues deployment intelligently and recovers later.
    """

    def __init__(
        self,
        operation_tracker: Optional[OperationTracker] = None,
        repair_engine: Optional[RepairEngine] = None,
        validator: Optional[EnvironmentValidator] = None,
        terminal_session: Optional[TerminalSession] = None,
    ) -> None:
        self._op_tracker = operation_tracker or OperationTracker()
        self._repair_engine = repair_engine or RepairEngine()
        self._validator = validator or EnvironmentValidator()
        self._terminal = terminal_session or TerminalSession()
        self._retry_queue = RetryQueue(operation_tracker=self._op_tracker)
        self._failure_analyzer = FailureAnalyzer()

        # Registered installers
        self._installers: Dict[str, AIInstallerBase] = {}

        # Execution state
        self._results: Dict[str, ToolDeploymentResult] = {}
        self._tool_order: List[str] = []
        self._is_running = False
        self._cancelled = False

    def register_installer(self, installer: AIInstallerBase) -> None:
        """Register an installer for execution."""
        self._installers[installer.tool_key] = installer
        self._repair_engine.register_installer(installer)

    def register_installers(self, installers: List[AIInstallerBase]) -> None:
        """Register multiple installers."""
        for installer in installers:
            self.register_installer(installer)

    @property
    def terminal(self) -> TerminalSession:
        return self._terminal

    @property
    def retry_queue(self) -> RetryQueue:
        return self._retry_queue

    @property
    def results(self) -> Dict[str, ToolDeploymentResult]:
        return dict(self._results)

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def execute_deployment(
        self,
        tool_keys: List[str],
        session_id: Optional[str] = None,
        skip_existing: bool = True,
        parallel: bool = False,
    ) -> Dict[str, ToolDeploymentResult]:
        """
        Execute deployment for a list of tools.

        This is the main entry point for real deployment execution.

        Args:
            tool_keys: Ordered list of tool keys to deploy
            session_id: Optional session ID for operation tracking
            skip_existing: Skip tools that are already installed
            parallel: Whether to run independent tools in parallel

        Returns:
            Dict mapping tool_key -> ToolDeploymentResult
        """
        self._is_running = True
        self._cancelled = False
        self._results = {}
        self._tool_order = list(tool_keys)

        if session_id:
            self._op_tracker.start_session()

        logger.info(
            "Starting deployment execution",
            tools=tool_keys,
            skip_existing=skip_existing,
            parallel=parallel,
        )

        try:
            if parallel:
                await self._execute_parallel(tool_keys, skip_existing)
            else:
                await self._execute_sequential(tool_keys, skip_existing)

            # Phase 2: Process retry queue
            await self._process_retry_queue()

            # Phase 3: Final validation pass
            await self._final_validation()

        except Exception as e:
            logger.error("Deployment execution error", error=str(e))
        finally:
            self._is_running = False

        return self._results

    async def _execute_sequential(
        self, tool_keys: List[str], skip_existing: bool
    ) -> None:
        """Execute tools sequentially (respects dependencies)."""
        for tool_key in tool_keys:
            if self._cancelled:
                logger.warning("Deployment cancelled during execution")
                break

            installer = self._installers.get(tool_key)
            if not installer:
                self._results[tool_key] = ToolDeploymentResult(
                    tool_key=tool_key,
                    tool_name=tool_key,
                    status="skipped",
                    error="No installer registered",
                )
                continue

            await self._deploy_tool(installer, skip_existing)

    async def _execute_parallel(
        self, tool_keys: List[str], skip_existing: bool
    ) -> None:
        """Execute independent tools in parallel."""
        # Group tools by dependency level
        levels = self._compute_dependency_levels(tool_keys)

        for level, level_tools in enumerate(levels):
            if self._cancelled:
                break

            logger.info(
                f"Executing dependency level {level}",
                tools=level_tools,
            )

            tasks = []
            for tool_key in level_tools:
                installer = self._installers.get(tool_key)
                if installer:
                    tasks.append(self._deploy_tool(installer, skip_existing))
                else:
                    self._results[tool_key] = ToolDeploymentResult(
                        tool_key=tool_key,
                        tool_name=tool_key,
                        status="skipped",
                        error="No installer registered",
                    )

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    def _compute_dependency_levels(self, tool_keys: List[str]) -> List[List[str]]:
        """Compute dependency levels for parallel execution ordering."""
        # Build dependency graph
        deps: Dict[str, Set[str]] = {}
        for tool_key in tool_keys:
            installer = self._installers.get(tool_key)
            if installer:
                deps[tool_key] = set(
                    d for d in installer.dependencies if d in tool_keys
                )
            else:
                deps[tool_key] = set()

        # Topological sort into levels
        levels = []
        remaining = set(tool_keys)

        while remaining:
            # Find tools with no remaining dependencies
            current_level = set()
            for tool_key in remaining:
                if not deps.get(tool_key, set()) & remaining:
                    current_level.add(tool_key)

            if not current_level:
                # Circular dependency - add remaining as-is
                levels.append(list(remaining))
                break

            levels.append(list(current_level))
            remaining -= current_level

        return levels

    async def _deploy_tool(
        self, installer: AIInstallerBase, skip_existing: bool
    ) -> None:
        """Deploy a single tool with full execution tracking."""
        tool_key = installer.tool_key
        tool_name = installer.tool_name
        start = time.time()

        logger.info(f"Deploying tool: {tool_name} ({tool_key})")

        # Phase 1: Detect existing installation
        op_id = self._op_tracker.start_operation(
            OperationType.VALIDATION,
            f"Detect {tool_name}",
            tool_key=tool_key,
        )

        try:
            detect_result = await installer.detect()

            if detect_result.status == InstallStatus.INSTALLED:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"version": detect_result.version},
                )

                if skip_existing:
                    self._results[tool_key] = ToolDeploymentResult(
                        tool_key=tool_key,
                        tool_name=tool_name,
                        status="installed",
                        version=detect_result.version,
                        duration_ms=(time.time() - start) * 1000,
                        operation_id=op_id,
                    )
                    logger.info(f"Tool already installed, skipping: {tool_name}")
                    return

            elif detect_result.status == InstallStatus.OUTDATED:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"version": detect_result.version, "outdated": True},
                )
                logger.info(f"Tool outdated, will upgrade: {tool_name}")

            else:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"installed": False},
                )
                logger.info(f"Tool not installed, will install: {tool_name}")

        except Exception as e:
            self._op_tracker.fail_operation(
                op_id, str(e), FailureCategory.UNKNOWN,
            )
            logger.warning(f"Detection failed for {tool_name}: {e}")

        # Phase 2: Install
        install_op_id = self._op_tracker.start_operation(
            OperationType.INSTALLER,
            f"Install {tool_name}",
            tool_key=tool_key,
        )

        try:
            install_result = await installer.install()

            # Populate reporting fields on InstallResult
            install_result.operation_id = install_op_id
            install_result.duration_ms = (time.time() - start) * 1000

            if install_result.status == InstallStatus.INSTALLED:
                self._op_tracker.finish_operation(
                    install_op_id, OperationStatus.SUCCEEDED,
                    result_data={
                        "version": install_result.version,
                        "path": install_result.install_path,
                    },
                )
                self._results[tool_key] = ToolDeploymentResult(
                    tool_key=tool_key,
                    tool_name=tool_name,
                    status="installed",
                    version=install_result.version,
                    duration_ms=(time.time() - start) * 1000,
                    operation_id=install_op_id,
                )
                logger.info(f"Successfully installed: {tool_name}")

            else:
                # Installation failed - analyze and queue for retry
                error_msg = install_result.error or "Installation failed"
                self._op_tracker.fail_operation(
                    install_op_id, error_msg, FailureCategory.UNKNOWN,
                )

                # Analyze the failure
                analysis = self._failure_analyzer.analyze(
                    tool_key=tool_key,
                    exit_code=-1,
                    stderr=error_msg,
                    error_message=error_msg,
                )

                # Queue for retry
                self._retry_queue.add(
                    tool_key=tool_key,
                    tool_name=tool_name,
                    operation_id=install_op_id,
                    failure_category=analysis.failure_category,
                    error_message=error_msg,
                )

                self._results[tool_key] = ToolDeploymentResult(
                    tool_key=tool_key,
                    tool_name=tool_name,
                    status="failed",
                    error=error_msg,
                    failure_analysis=analysis,
                    duration_ms=(time.time() - start) * 1000,
                    operation_id=install_op_id,
                )
                logger.warning(f"Installation failed for {tool_name}: {error_msg[:200]}")

        except Exception as e:
            error_msg = str(e)
            self._op_tracker.fail_operation(
                install_op_id, error_msg, FailureCategory.UNKNOWN,
            )

            analysis = self._failure_analyzer.analyze(
                tool_key=tool_key,
                exit_code=-3,
                error_message=error_msg,
            )

            self._retry_queue.add(
                tool_key=tool_key,
                tool_name=tool_name,
                operation_id=install_op_id,
                failure_category=analysis.failure_category,
                error_message=error_msg,
            )

            self._results[tool_key] = ToolDeploymentResult(
                tool_key=tool_key,
                tool_name=tool_name,
                status="failed",
                error=error_msg,
                failure_analysis=analysis,
                duration_ms=(time.time() - start) * 1000,
                operation_id=install_op_id,
            )
            logger.error(f"Exception during {tool_name} installation: {error_msg[:200]}")

    async def _process_retry_queue(self) -> None:
        """Process the retry queue - retry failed operations."""
        if not self._retry_queue.has_pending():
            logger.info("No pending retries")
            return

        logger.info(
            "Processing retry queue",
            pending=self._retry_queue.get_summary()["pending_retries"],
        )

        max_retry_rounds = 3
        for round_num in range(max_retry_rounds):
            if self._cancelled:
                break

            if not self._retry_queue.has_due():
                if self._retry_queue.has_pending():
                    # Wait for backoff timers
                    logger.info("Waiting for retry backoff timers...")
                    await asyncio.sleep(5)
                    continue
                break

            due_entries = self._retry_queue.get_due_entries()
            if not due_entries:
                break

            logger.info(
                f"Retry round {round_num + 1}/{max_retry_rounds}",
                due_count=len(due_entries),
            )

            for entry in due_entries:
                if self._cancelled:
                    break

                installer = self._installers.get(entry.tool_key)
                if not installer:
                    self._retry_queue.mark_skipped(entry.tool_key)
                    continue

                # Attempt repair first
                repair_result = await self._repair_engine.repair_tool(entry.tool_key)
                if repair_result.status.value == "succeeded":
                    # Verify after repair
                    verify_result = await installer.verify()
                    if verify_result.status == InstallStatus.INSTALLED:
                        self._results[entry.tool_key].status = "installed"
                        self._results[entry.tool_key].version = verify_result.version
                        self._results[entry.tool_key].error = None
                        self._retry_queue.mark_completed(entry.tool_key)
                        logger.info(
                            f"Retry successful for {entry.tool_name} (after repair)"
                        )
                        continue

                # Retry installation
                retry_op_id = self._op_tracker.start_retry(
                    entry.operation_id, entry.attempt + 1
                )

                try:
                    install_result = await installer.install()

                    if install_result.status == InstallStatus.INSTALLED:
                        self._op_tracker.finish_operation(
                            retry_op_id, OperationStatus.SUCCEEDED,
                            result_data={"version": install_result.version},
                        )
                        self._results[entry.tool_key].status = "installed"
                        self._results[entry.tool_key].version = install_result.version
                        self._results[entry.tool_key].error = None
                        self._results[entry.tool_key].retry_attempts = entry.attempt + 1
                        self._retry_queue.mark_completed(entry.tool_key)
                        logger.info(
                            f"Retry successful for {entry.tool_name} "
                            f"(attempt {entry.attempt + 1})"
                        )
                    else:
                        self._op_tracker.fail_operation(
                            retry_op_id,
                            install_result.error or "Retry failed",
                            FailureCategory.UNKNOWN,
                        )
                        self._retry_queue.mark_attempted(entry.tool_key)
                        logger.warning(
                            f"Retry failed for {entry.tool_name} "
                            f"(attempt {entry.attempt + 1}/{entry.max_retries})"
                        )

                except Exception as e:
                    self._op_tracker.fail_operation(
                        retry_op_id, str(e), FailureCategory.UNKNOWN,
                    )
                    self._retry_queue.mark_attempted(entry.tool_key)
                    logger.error(
                        f"Retry exception for {entry.tool_name}: {str(e)[:200]}"
                    )

        # Report exhausted retries
        exhausted = self._retry_queue.get_exhausted_tools()
        if exhausted:
            logger.warning(
                "Some tools exhausted retries",
                tools=[e.tool_key for e in exhausted],
            )
            for entry in exhausted:
                self._results[entry.tool_key].status = "failed"
                self._results[entry.tool_key].error = (
                    f"Failed after {entry.max_retries} retry attempts"
                )

    async def _final_validation(self) -> None:
        """Run final validation pass after all installations."""
        logger.info("Running final validation pass")

        # Check all requested tools
        installed_tools = []
        failed_tools = []

        for tool_key in self._tool_order:
            result = self._results.get(tool_key)
            if result and result.status == "installed":
                installed_tools.append(tool_key)
            else:
                failed_tools.append(tool_key)

        # Run environment validator
        validation = await self._validator.validate_all(
            required_tools=installed_tools
        )

        # Log validation results
        if validation.issues:
            logger.warning(
                "Validation found issues",
                errors=len(validation.errors),
                warnings=len(validation.warnings),
            )
            for issue in validation.issues:
                logger.info(
                    f"Validation issue: [{issue.severity}] "
                    f"{issue.tool_key}: {issue.message}"
                )

        # Check for tools that are actually installed but reported as failed
        for tool_key in failed_tools:
            installer = self._installers.get(tool_key)
            if installer:
                try:
                    detect = await installer.detect()
                    if detect.status == InstallStatus.INSTALLED:
                        # Tool is actually installed despite failure report
                        self._results[tool_key].status = "installed"
                        self._results[tool_key].version = detect.version
                        self._results[tool_key].error = None
                        logger.info(
                            f"Tool {tool_key} is actually installed despite previous failure"
                        )
                except Exception:
                    pass

        logger.info(
            "Final validation complete",
            installed=len(installed_tools),
            failed=len(failed_tools),
            validation_issues=len(validation.issues),
        )

    async def execute_repair(self, tool_key: str) -> bool:
        """Execute repair for a specific tool."""
        installer = self._installers.get(tool_key)
        if not installer:
            logger.warning(f"No installer for repair: {tool_key}")
            return False

        result = await self._repair_engine.repair_tool(tool_key)
        success = result.status.value == "succeeded"

        if success:
            self._results[tool_key] = ToolDeploymentResult(
                tool_key=tool_key,
                tool_name=getattr(installer, "tool_name", tool_key),
                status="installed",
                duration_ms=result.duration_ms or 0,
            )

        return success

    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None,
    ) -> TerminalResult:
        """Execute a command via the terminal session."""
        return await self._terminal.execute(command, timeout=timeout)

    def get_summary(self) -> Dict[str, Any]:
        """Get a comprehensive deployment summary."""
        total = len(self._results)
        installed = sum(1 for r in self._results.values() if r.status == "installed")
        failed = sum(1 for r in self._results.values() if r.status == "failed")
        skipped = sum(1 for r in self._results.values() if r.status == "skipped")

        total_duration = sum(r.duration_ms for r in self._results.values())

        return {
            "total_tools": total,
            "installed": installed,
            "failed": failed,
            "skipped": skipped,
            "success_rate": round((installed / total * 100), 1) if total else 0,
            "total_duration_ms": round(total_duration, 1),
            "retry_queue": self._retry_queue.get_summary(),
            "terminal_stats": self._terminal.get_stats(),
            "tools": {
                k: v.to_dict() for k, v in self._results.items()
            },
        }

    def cancel(self) -> None:
        """Cancel the current deployment execution."""
        self._cancelled = True
        logger.info("Deployment execution cancelled")
