"""
Corax Orchestrator - Developer Tool Deployment Entry Point.

Provides a focused entry point for deploying developer tools
(Git, Python, Node.js) using the existing deployment infrastructure.

Reuses:
- DeploymentSession for lifecycle management
- DeploymentExecutor for execution
- DevInstallerBase for installation logic
- RetryQueue for failure recovery
- FailureAnalyzer for error classification
- OperationTracker for operation tracking
- EnvironmentValidator for validation
- WindowsUtils for winget/direct installers

This is NOT a redesign. It is a focused entry point that wires
existing components together for dev-tool deployment.
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import time
import os
import json
from pathlib import Path

from src.core.logging import get_logger, setup_logging
from src.deployment.operations import OperationTracker, OperationType, OperationStatus, FailureCategory
from src.deployment.execution.executor import DeploymentExecutor, ToolDeploymentResult
from src.deployment.execution.session import DeploymentSession, DeploymentSessionResult
from src.deployment.execution.terminal import TerminalSession
from src.deployment.execution.retry_queue import RetryQueue
from src.deployment.execution.failure_analyzer import FailureAnalyzer
from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus
from src.deployment.installers.dev_base import DevInstallerBase
from src.deployment.validation import EnvironmentValidator, ValidationResult

logger = get_logger(__name__)


# Supported dev tools for this phase
DEV_TOOL_INSTALLERS: Dict[str, type] = {}


def _register_dev_installers() -> None:
    """Lazy-register dev tool installer classes."""
    global DEV_TOOL_INSTALLERS
    if DEV_TOOL_INSTALLERS:
        return
    try:
        from src.deployment.installers.git_installer import GitInstaller
        DEV_TOOL_INSTALLERS["git"] = GitInstaller
    except ImportError as e:
        logger.warning("Git installer not available", error=str(e))

    try:
        from src.deployment.installers.python_installer import PythonInstaller
        DEV_TOOL_INSTALLERS["python"] = PythonInstaller
    except ImportError as e:
        logger.warning("Python installer not available", error=str(e))

    try:
        from src.deployment.installers.node_installer import NodeInstaller
        DEV_TOOL_INSTALLERS["nodejs"] = NodeInstaller
    except ImportError as e:
        logger.warning("Node.js installer not available", error=str(e))


@dataclass
class DevDeployReport:
    """
    Structured deployment report for dev tools.

    Contains all information needed for the reporting requirements:
    - operation IDs
    - command executed
    - duration
    - exit codes
    - retry attempts
    - validation results
    """
    session_id: str
    status: str  # "completed", "partial", "failed"
    started_at: str
    completed_at: str
    duration_seconds: float
    tools_requested: List[str]
    tools_installed: List[str]
    tools_failed: List[str]
    tools_skipped: List[str]
    success_rate: float
    tool_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    validation: Optional[Dict[str, Any]] = None
    retry_summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    report_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_type": "dev_deployment",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "tools_requested": self.tools_requested,
            "tools_installed": self.tools_installed,
            "tools_failed": self.tools_failed,
            "tools_skipped": self.tools_skipped,
            "success_rate": round(self.success_rate, 1),
            "tool_details": self.tool_details,
            "validation": self.validation,
            "retry_summary": self.retry_summary,
            "errors": self.errors,
            "report_path": self.report_path,
        }


class DevDeploy:
    """
    Focused entry point for developer tool deployment.

    Wires existing components together for deploying Git, Python, and Node.js.
    Uses the same execution engine, retry queue, failure analyzer, and
    reporting infrastructure as the full deployment system.

    Usage:
        deployer = DevDeploy()
        report = await deployer.deploy(["git", "python", "nodejs"])
    """

    def __init__(
        self,
        data_dir: str = "data",
        report_dir: Optional[str] = None,
    ) -> None:
        self._data_dir = data_dir
        self._report_dir = report_dir or os.path.join(data_dir, "reports")
        self._op_tracker = OperationTracker()
        self._terminal = TerminalSession()
        self._validator = EnvironmentValidator()
        self._executor = DeploymentExecutor(
            operation_tracker=self._op_tracker,
            validator=self._validator,
            terminal_session=self._terminal,
        )
        self._session = DeploymentSession(
            executor=self._executor,
            operation_tracker=self._op_tracker,
            validator=self._validator,
            data_dir=data_dir,
        )

        # Register dev tool installers
        _register_dev_installers()
        for tool_key, installer_cls in DEV_TOOL_INSTALLERS.items():
            installer = installer_cls(operation_tracker=self._op_tracker)
            self._executor.register_installer(installer)

    @property
    def executor(self) -> DeploymentExecutor:
        return self._executor

    @property
    def session(self) -> DeploymentSession:
        return self._session

    @property
    def available_tools(self) -> List[str]:
        """Get list of available dev tools."""
        return list(DEV_TOOL_INSTALLERS.keys())

    async def deploy(
        self,
        tools: Optional[List[str]] = None,
        skip_existing: bool = True,
        parallel: bool = False,
        progress_callback: Optional[Callable[[str, float], Awaitable[None]]] = None,
    ) -> DevDeployReport:
        """
        Deploy developer tools.

        Args:
            tools: List of tool keys to deploy (default: all available)
            skip_existing: Skip already-installed tools
            parallel: Run independent tools in parallel
            progress_callback: Optional async callback (tool_key, progress_pct)

        Returns:
            DevDeployReport with complete deployment results
        """
        if tools is None:
            tools = self.available_tools

        # Validate requested tools
        invalid_tools = [t for t in tools if t not in DEV_TOOL_INSTALLERS]
        if invalid_tools:
            logger.warning(
                "Unknown tools requested, will be skipped",
                invalid=invalid_tools,
            )

        valid_tools = [t for t in tools if t in DEV_TOOL_INSTALLERS]
        if not valid_tools:
            return DevDeployReport(
                session_id="none",
                status="failed",
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0.0,
                tools_requested=tools,
                tools_installed=[],
                tools_failed=[],
                tools_skipped=tools,
                success_rate=0.0,
                errors=["No valid tools requested"],
            )

        start_time = time.time()
        session_id = self._session.start_session(profile_name="dev_tools")

        logger.info(
            "Starting dev tool deployment",
            session_id=session_id,
            tools=valid_tools,
            skip_existing=skip_existing,
        )

        try:
            # Execute deployment using the existing engine
            results = await self._executor.execute_deployment(
                tool_keys=valid_tools,
                session_id=session_id,
                skip_existing=skip_existing,
                parallel=parallel,
            )

            # Build detailed tool results
            tool_details: Dict[str, Dict[str, Any]] = {}
            for tool_key, result in results.items():
                detail = result.to_dict()
                # Add validation results for each tool
                installer = self._executor._installers.get(tool_key)
                if installer and result.status == "installed":
                    try:
                        # Run version commands
                        version_info = await self._get_version_info(tool_key)
                        detail["version_info"] = version_info
                    except Exception as e:
                        detail["version_info"] = {"error": str(e)}
                tool_details[tool_key] = detail

            # Run final validation
            installed_tools = [
                k for k, v in results.items() if v.status == "installed"
            ]
            validation = await self._validator.validate_all(
                required_tools=installed_tools
            )

            # Build report
            report = self._build_report(
                session_id=session_id,
                start_time=start_time,
                tools_requested=valid_tools,
                results=results,
                tool_details=tool_details,
                validation=validation,
            )

            # Save report
            report_path = await self._save_report(report)
            report.report_path = report_path

            logger.info(
                "Dev tool deployment complete",
                session_id=session_id,
                status=report.status,
                installed=report.tools_installed,
                failed=report.tools_failed,
                duration=round(report.duration_seconds, 1),
            )

            return report

        except Exception as e:
            logger.error("Dev tool deployment failed", error=str(e))
            return DevDeployReport(
                session_id=session_id,
                status="failed",
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=time.time() - start_time,
                tools_requested=valid_tools,
                tools_installed=[],
                tools_failed=valid_tools,
                tools_skipped=[],
                success_rate=0.0,
                errors=[str(e)],
            )

    async def _get_version_info(self, tool_key: str) -> Dict[str, Any]:
        """Get version information for a tool."""
        version_info: Dict[str, Any] = {}

        if tool_key == "git":
            result = await self._terminal.execute(
                "git --version", timeout=10
            )
            version_info["git_version"] = result.stdout.strip() if result.succeeded else None

        elif tool_key == "python":
            result = await self._terminal.execute(
                "python --version", timeout=10
            )
            version_info["python_version"] = result.stdout.strip() if result.succeeded else None
            # Also check pip
            pip_result = await self._terminal.execute(
                "pip --version", timeout=10
            )
            version_info["pip_version"] = pip_result.stdout.strip() if pip_result.succeeded else None

        elif tool_key == "nodejs":
            node_result = await self._terminal.execute(
                "node --version", timeout=10
            )
            version_info["node_version"] = node_result.stdout.strip() if node_result.succeeded else None
            # Also check npm
            npm_result = await self._terminal.execute(
                "npm --version", timeout=10
            )
            version_info["npm_version"] = npm_result.stdout.strip() if npm_result.succeeded else None

        # PATH verification
        import shutil
        binary_map = {
            "git": "git",
            "python": "python",
            "nodejs": "node",
        }
        binary = binary_map.get(tool_key)
        if binary:
            path = shutil.which(binary)
            version_info["path"] = path
            version_info["in_path"] = path is not None

        return version_info

    def _build_report(
        self,
        session_id: str,
        start_time: float,
        tools_requested: List[str],
        results: Dict[str, ToolDeploymentResult],
        tool_details: Dict[str, Dict[str, Any]],
        validation: ValidationResult,
    ) -> DevDeployReport:
        """Build a structured deployment report."""
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

        if len(tools_failed) == 0:
            status = "completed"
        elif len(tools_installed) > 0:
            status = "partial"
        else:
            status = "failed"

        return DevDeployReport(
            session_id=session_id,
            status=status,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=time.time() - start_time,
            tools_requested=tools_requested,
            tools_installed=tools_installed,
            tools_failed=tools_failed,
            tools_skipped=tools_skipped,
            success_rate=success_rate,
            tool_details=tool_details,
            validation=validation.to_dict(),
            retry_summary=self._executor.retry_queue.get_summary(),
        )

    async def _save_report(self, report: DevDeployReport) -> str:
        """Save the deployment report to disk."""
        os.makedirs(self._report_dir, exist_ok=True)
        report_path = os.path.join(
            self._report_dir,
            f"dev_deploy_{report.session_id}.json",
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        logger.info("Dev deploy report saved", path=report_path)
        return report_path

    async def detect_all(self) -> Dict[str, InstallResult]:
        """Detect installation status for all dev tools."""
        results = {}
        for tool_key, installer_cls in DEV_TOOL_INSTALLERS.items():
            installer = installer_cls(operation_tracker=self._op_tracker)
            try:
                result = await installer.detect()
                results[tool_key] = result
            except Exception as e:
                results[tool_key] = InstallResult(
                    tool_name=tool_key,
                    status=InstallStatus.FAILED,
                    error=str(e),
                )
        return results

    async def validate_environment(self) -> ValidationResult:
        """Run full environment validation."""
        return await self._validator.validate_all(
            required_tools=list(DEV_TOOL_INSTALLERS.keys())
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the deployment state."""
        return {
            "available_tools": self.available_tools,
            "executor_summary": self._executor.get_summary(),
        }
