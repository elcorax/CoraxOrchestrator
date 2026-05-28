"""
Corax Orchestrator - Deployment Session.

Manages a complete deployment session from start to finish.
Handles session lifecycle, state persistence, report generation,
and provides a high-level API for the orchestrator.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import time
import os
import json
from pathlib import Path

from src.core.logging import get_logger
from src.deployment.operations import OperationTracker, OperationStatus
from src.deployment.execution.executor import DeploymentExecutor, ToolDeploymentResult
from src.deployment.execution.terminal import TerminalSession
from src.deployment.execution.retry_queue import RetryQueue
from src.deployment.execution.failure_analyzer import FailureAnalyzer
from src.deployment.installers.base import AIInstallerBase, InstallStatus
from src.deployment.validation import EnvironmentValidator, ValidationResult
from src.deployment.repair.engine import RepairEngine

logger = get_logger(__name__)


@dataclass
class DeploymentSessionResult:
    """Complete result of a deployment session."""
    session_id: str
    status: str  # "completed", "partial", "failed"
    started_at: str
    completed_at: str
    duration_seconds: float
    profile_name: str
    tools_requested: List[str]
    tools_installed: List[str]
    tools_failed: List[str]
    tools_skipped: List[str]
    success_rate: float
    retry_summary: Dict[str, Any]
    validation: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    report_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "profile_name": self.profile_name,
            "tools_requested": self.tools_requested,
            "tools_installed": self.tools_installed,
            "tools_failed": self.tools_failed,
            "tools_skipped": self.tools_skipped,
            "success_rate": round(self.success_rate, 1),
            "retry_summary": self.retry_summary,
            "validation": self.validation,
            "errors": self.errors,
            "report_path": self.report_path,
        }


class DeploymentSession:
    """
    Manages a complete deployment session lifecycle.

    Features:
    - Session start/stop lifecycle
    - State persistence across restarts
    - Deployment report generation
    - Failure summary and analysis
    - Retry queue management
    - Validation integration
    """

    def __init__(
        self,
        executor: Optional[DeploymentExecutor] = None,
        operation_tracker: Optional[OperationTracker] = None,
        validator: Optional[EnvironmentValidator] = None,
        data_dir: str = "data",
    ) -> None:
        self._op_tracker = operation_tracker or OperationTracker()
        self._executor = executor or DeploymentExecutor(
            operation_tracker=self._op_tracker,
            validator=validator or EnvironmentValidator(),
        )
        self._validator = validator or EnvironmentValidator()
        self._data_dir = data_dir
        self._session_id: Optional[str] = None
        self._started_at: Optional[str] = None
        self._profile_name: str = "unknown"
        self._errors: List[str] = []

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def executor(self) -> DeploymentExecutor:
        return self._executor

    @property
    def is_active(self) -> bool:
        return self._session_id is not None

    def start_session(self, profile_name: str = "custom") -> str:
        """Start a new deployment session."""
        self._session_id = self._op_tracker.start_session()
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._profile_name = profile_name
        self._errors = []
        logger.info(
            "Deployment session started",
            session_id=self._session_id,
            profile=profile_name,
        )
        return self._session_id

    async def deploy_tools(
        self,
        tool_keys: List[str],
        skip_existing: bool = True,
        parallel: bool = False,
    ) -> DeploymentSessionResult:
        """
        Deploy a list of tools in a managed session.

        Args:
            tool_keys: Ordered list of tool keys to deploy
            skip_existing: Skip already-installed tools
            parallel: Run independent tools in parallel

        Returns:
            DeploymentSessionResult with complete session results
        """
        if not self._session_id:
            self.start_session()

        start_time = time.time()

        try:
            # Execute deployment
            results = await self._executor.execute_deployment(
                tool_keys=tool_keys,
                session_id=self._session_id,
                skip_existing=skip_existing,
                parallel=parallel,
            )

            # Build session result
            session_result = self._build_session_result(results, start_time)

            # Save state
            await self._save_session_state(session_result)

            # Generate report
            report_path = await self._generate_report(session_result, results)
            session_result.report_path = report_path

            return session_result

        except Exception as e:
            self._errors.append(str(e))
            logger.error("Session deployment failed", error=str(e))

            return DeploymentSessionResult(
                session_id=self._session_id or "unknown",
                status="failed",
                started_at=self._started_at or datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=time.time() - start_time,
                profile_name=self._profile_name,
                tools_requested=tool_keys,
                tools_installed=[],
                tools_failed=tool_keys,
                tools_skipped=[],
                success_rate=0.0,
                retry_summary={},
                errors=self._errors,
            )

    def _build_session_result(
        self,
        results: Dict[str, ToolDeploymentResult],
        start_time: float,
    ) -> DeploymentSessionResult:
        """Build a DeploymentSessionResult from execution results."""
        tools_requested = list(results.keys())
        tools_installed = [
            k for k, v in results.items() if v.status == "installed"
        ]
        tools_failed = [
            k for k, v in results.items() if v.status == "failed"
        ]
        tools_skipped = [
            k for k, v in results.items() if v.status == "skipped"
        ]

        total = len(tools_requested)
        success_rate = (len(tools_installed) / total * 100) if total else 0

        # Determine overall status
        if len(tools_failed) == 0:
            status = "completed"
        elif len(tools_installed) > 0:
            status = "partial"
        else:
            status = "failed"

        return DeploymentSessionResult(
            session_id=self._session_id or "unknown",
            status=status,
            started_at=self._started_at or datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=time.time() - start_time,
            profile_name=self._profile_name,
            tools_requested=tools_requested,
            tools_installed=tools_installed,
            tools_failed=tools_failed,
            tools_skipped=tools_skipped,
            success_rate=success_rate,
            retry_summary=self._executor.retry_queue.get_summary(),
            errors=self._errors,
        )

    async def _save_session_state(
        self, session_result: DeploymentSessionResult
    ) -> None:
        """Save session state for persistence across restarts."""
        state_dir = os.path.join(self._data_dir, "persistence")
        os.makedirs(state_dir, exist_ok=True)

        state_path = os.path.join(
            state_dir, f"session_{self._session_id}.json"
        )

        state = {
            "session_id": self._session_id,
            "status": session_result.status,
            "started_at": session_result.started_at,
            "completed_at": session_result.completed_at,
            "profile_name": self._profile_name,
            "tools_requested": session_result.tools_requested,
            "tools_installed": session_result.tools_installed,
            "tools_failed": session_result.tools_failed,
            "tools_skipped": session_result.tools_skipped,
            "errors": self._errors,
            "retry_queue": self._executor.retry_queue.get_summary(),
            "terminal_stats": self._executor.terminal.get_stats(),
        }

        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

        logger.info("Session state saved", path=state_path)

        # Save operation records
        ops_path = os.path.join(
            state_dir, f"operations_{self._session_id}.json"
        )
        self._op_tracker.save_to_file(ops_path)

    async def _generate_report(
        self,
        session_result: DeploymentSessionResult,
        results: Dict[str, ToolDeploymentResult],
    ) -> str:
        """Generate a deployment report."""
        report_dir = os.path.join(self._data_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)

        report_path = os.path.join(
            report_dir, f"deployment_{self._session_id}.json"
        )

        # Run validation
        validation = await self._validator.validate_all(
            required_tools=session_result.tools_installed
        )
        session_result.validation = validation.to_dict()

        report = {
            "report_type": "deployment_session",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "session": session_result.to_dict(),
            "tool_results": {
                k: v.to_dict() for k, v in results.items()
            },
            "operation_summary": self._op_tracker.get_summary(),
            "terminal_history": [
                r.to_dict() for r in self._executor.terminal.history
            ],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info("Deployment report generated", path=report_path)
        return report_path

    async def resume_session(
        self, session_id: str
    ) -> Optional[DeploymentSessionResult]:
        """
        Resume a previous deployment session.

        Loads saved state and retries failed tools.

        Args:
            session_id: Session ID to resume

        Returns:
            DeploymentSessionResult or None if session not found
        """
        state_path = os.path.join(
            self._data_dir, "persistence", f"session_{session_id}.json"
        )

        if not os.path.exists(state_path):
            logger.warning(f"Session state not found: {session_id}")
            return None

        # Load state
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        self._session_id = session_id
        self._started_at = state.get("started_at")
        self._profile_name = state.get("profile_name", "resumed")
        self._errors = state.get("errors", [])

        # Load operation records
        ops_path = os.path.join(
            self._data_dir, "persistence", f"operations_{session_id}.json"
        )
        if os.path.exists(ops_path):
            self._op_tracker.load_from_file(ops_path)

        # Get failed tools from saved state
        failed_tools = state.get("tools_failed", [])
        if not failed_tools:
            logger.info(f"Session {session_id} has no failed tools to retry")
            return None

        logger.info(
            f"Resuming session {session_id}",
            failed_tools=failed_tools,
        )

        # Retry failed tools
        start_time = time.time()
        results = await self._executor.execute_deployment(
            tool_keys=failed_tools,
            session_id=session_id,
            skip_existing=False,
        )

        session_result = self._build_session_result(results, start_time)
        await self._save_session_state(session_result)
        report_path = await self._generate_report(session_result, results)
        session_result.report_path = report_path

        return session_result

    def get_latest_session(self) -> Optional[str]:
        """Get the most recent session ID from saved state."""
        state_dir = os.path.join(self._data_dir, "persistence")
        if not os.path.exists(state_dir):
            return None

        sessions = [
            f for f in os.listdir(state_dir)
            if f.startswith("session_") and f.endswith(".json")
        ]

        if not sessions:
            return None

        # Sort by modification time (newest first)
        sessions.sort(
            key=lambda f: os.path.getmtime(os.path.join(state_dir, f)),
            reverse=True,
        )

        # Extract session ID from filename
        return sessions[0].replace("session_", "").replace(".json", "")

    def end_session(self) -> None:
        """End the current session."""
        if self._session_id:
            logger.info(
                "Deployment session ended",
                session_id=self._session_id,
            )
        self._session_id = None
        self._started_at = None

    async def resume_after_reboot(
        self, session_id: Optional[str] = None
    ) -> Optional[DeploymentSessionResult]:
        """
        Resume deployment after a system reboot.

        Automatically detects the most recent incomplete session and
        retries all failed tools. Handles the case where some tools
        may have been partially installed before the reboot.

        Args:
            session_id: Optional specific session to resume.
                        If None, resumes the latest incomplete session.

        Returns:
            DeploymentSessionResult or None if no session to resume.
        """
        target_session = session_id or self.get_latest_session()
        if not target_session:
            logger.info("No previous session found to resume after reboot")
            return None

        logger.info(
            "Resuming deployment after reboot",
            session_id=target_session,
        )

        # Load the saved state
        state_path = os.path.join(
            self._data_dir, "persistence", f"session_{target_session}.json"
        )
        if not os.path.exists(state_path):
            logger.warning(
                f"Session state not found for reboot resume: {target_session}"
            )
            return None

        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Check if session was already complete
        if state.get("status") == "completed":
            logger.info(
                f"Session {target_session} was already completed"
            )
            return None

        # Re-detect all tools to see what survived the reboot
        failed_tools = state.get("tools_failed", [])
        installed_tools = state.get("tools_installed", [])

        # Some "failed" tools may actually be installed after reboot
        # (e.g., if the installer required a reboot to complete)
        recheck_failed = []
        for tool_key in failed_tools:
            installer = self._executor._installers.get(tool_key)
            if installer:
                try:
                    detect = await installer.detect()
                    if detect.status == InstallStatus.INSTALLED:
                        installed_tools.append(tool_key)
                        logger.info(
                            f"Tool {tool_key} is now installed after reboot"
                        )
                        continue
                except Exception:
                    pass
            recheck_failed.append(tool_key)

        if not recheck_failed:
            logger.info("All tools are now installed after reboot")
            return DeploymentSessionResult(
                session_id=target_session,
                status="completed",
                started_at=state.get("started_at", ""),
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0.0,
                profile_name=state.get("profile_name", "reboot_resume"),
                tools_requested=state.get("tools_requested", []),
                tools_installed=installed_tools,
                tools_failed=[],
                tools_skipped=state.get("tools_skipped", []),
                success_rate=100.0,
                retry_summary={},
            )

        # Resume with remaining failed tools
        return await self.resume_session(target_session)
