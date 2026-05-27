"""
Corax Orchestrator - Task Orchestrator Module.

Orchestrates the complete deployment workflow by coordinating
all other modules. Manages task lifecycle, progress tracking,
and error recovery.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio
from uuid import uuid4

from src.core.logging import get_logger, set_correlation_id
from src.core.exceptions import CoraxError
from src.modules.system_scanner import SystemScanner, ScanResult
from src.modules.environment_analyzer import EnvironmentAnalyzer, EnvironmentAnalysis
from src.modules.installer_engine import InstallerEngine, InstallerResult, InstallerStatus
from src.modules.tool_registry import ToolRegistry
from src.modules.model_manager import ModelManager, ModelProvider
from src.modules.permission_manager import PermissionManager, PermissionLevel
from src.modules.self_healing import SelfHealingEngine, RecoveryResult
from src.modules.state_persistence import StatePersistence
from src.modules.reporting import ReportingEngine, DeploymentReport

logger = get_logger(__name__)


class TaskStatus(Enum):
    """Status of a deployment task."""
    PENDING = "pending"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    INSTALLING = "installing"
    CONFIGURING = "configuring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    """Progress information for a deployment task."""
    status: TaskStatus = TaskStatus.PENDING
    progress_percent: float = 0.0
    current_step: str = ""
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "current_step": self.current_step,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class DeploymentTask:
    """A complete deployment task with all state."""
    task_id: str = field(default_factory=lambda: str(uuid4()))
    tools_to_install: List[str] = field(default_factory=list)
    models_to_pull: List[str] = field(default_factory=list)
    progress: TaskProgress = field(default_factory=TaskProgress)
    scan_result: Optional[ScanResult] = None
    analysis: Optional[EnvironmentAnalysis] = None
    install_results: Dict[str, InstallerResult] = field(default_factory=dict)
    recovery_results: List[RecoveryResult] = field(default_factory=list)
    report: Optional[DeploymentReport] = None
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tools_to_install": self.tools_to_install,
            "models_to_pull": self.models_to_pull,
            "progress": self.progress.to_dict(),
            "install_results": {
                k: v.to_dict() for k, v in self.install_results.items()
            },
            "config": self.config,
        }


class TaskOrchestrator:
    """
    Main orchestrator for deployment tasks.

    Coordinates the complete deployment workflow:
    1. System scanning
    2. Environment analysis
    3. Tool installation
    4. Model management
    5. Error recovery
    6. Report generation
    """

    def __init__(
        self,
        scanner: Optional[SystemScanner] = None,
        analyzer: Optional[EnvironmentAnalyzer] = None,
        installer: Optional[InstallerEngine] = None,
        model_manager: Optional[ModelManager] = None,
        permission_manager: Optional[PermissionManager] = None,
        healing_engine: Optional[SelfHealingEngine] = None,
        persistence: Optional[StatePersistence] = None,
        reporting: Optional[ReportingEngine] = None,
    ) -> None:
        self.scanner = scanner or SystemScanner()
        self.analyzer = analyzer or EnvironmentAnalyzer()
        self.installer = installer or InstallerEngine()
        self.model_manager = model_manager or ModelManager()
        self.permission_manager = permission_manager or PermissionManager()
        self.healing_engine = healing_engine or SelfHealingEngine()
        self.persistence = persistence or StatePersistence()
        self.reporting = reporting or ReportingEngine()

        self._current_task: Optional[DeploymentTask] = None
        self._progress_callbacks: List[Callable[[TaskProgress], Awaitable[None]]] = []

    def on_progress(self, callback: Callable[[TaskProgress], Awaitable[None]]) -> None:
        """Register a progress callback."""
        self._progress_callbacks.append(callback)

    async def _notify_progress(self) -> None:
        """Notify all progress callbacks."""
        if not self._current_task:
            return
        for callback in self._progress_callbacks:
            try:
                await callback(self._current_task.progress)
            except Exception as e:
                logger.error("Progress callback failed", error=str(e))

    async def run_deployment(
        self,
        tools: Optional[List[str]] = None,
        models: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> DeploymentTask:
        """
        Run a complete deployment workflow.

        Args:
            tools: List of tool names to install
            models: List of model names to pull
            config: Optional task configuration

        Returns:
            DeploymentTask with all results
        """
        # Set correlation ID for this task
        task_id = str(uuid4())
        set_correlation_id(task_id)

        task = DeploymentTask(
            task_id=task_id,
            tools_to_install=tools or [],
            models_to_pull=models or [],
            config=config or {},
        )
        self._current_task = task

        start_time = datetime.now(timezone.utc)

        try:
            # Phase 1: System Scan
            await self._phase_scan(task)

            # Phase 2: Environment Analysis
            await self._phase_analyze(task)

            # Phase 3: Permission Check
            await self._phase_permissions(task)

            # Phase 4: Tool Installation
            await self._phase_install(task)

            # Phase 5: Model Management
            await self._phase_models(task)

            # Phase 6: Report Generation
            await self._phase_report(task, start_time)

            task.progress.status = TaskStatus.COMPLETED
            task.progress.message = "Deployment completed successfully"

        except CoraxError as e:
            task.progress.status = TaskStatus.FAILED
            task.progress.errors.append(str(e))
            logger.error("Deployment failed", error=str(e))

            # Attempt recovery
            recovery_result = await self.healing_engine.attempt_recovery(
                e, context={"task_id": task.task_id}
            )
            task.recovery_results.append(recovery_result)

        except Exception as e:
            task.progress.status = TaskStatus.FAILED
            task.progress.errors.append(f"Unexpected error: {e}")
            logger.error("Unexpected deployment error", error=str(e))

        finally:
            task.progress.completed_at = datetime.now(timezone.utc).isoformat()
            await self._notify_progress()

            # Persist task state
            await self.persistence.save_task_state(task.task_id, task.to_dict())

        return task

    async def _phase_scan(self, task: DeploymentTask) -> None:
        """Phase 1: Scan the system."""
        task.progress.status = TaskStatus.SCANNING
        task.progress.current_step = "Scanning system hardware and software"
        task.progress.progress_percent = 10
        await self._notify_progress()

        task.scan_result = await self.scanner.scan()

        task.progress.progress_percent = 25
        await self._notify_progress()

    async def _phase_analyze(self, task: DeploymentTask) -> None:
        """Phase 2: Analyze the environment."""
        task.progress.status = TaskStatus.ANALYZING
        task.progress.current_step = "Analyzing environment readiness"
        task.progress.progress_percent = 30
        await self._notify_progress()

        if task.scan_result:
            task.analysis = self.analyzer.analyze(task.scan_result)
            task.progress.warnings = task.analysis.warnings

        task.progress.progress_percent = 45
        await self._notify_progress()

    async def _phase_permissions(self, task: DeploymentTask) -> None:
        """Phase 3: Check and request permissions."""
        task.progress.current_step = "Checking permissions"
        task.progress.progress_percent = 50
        await self._notify_progress()

        plan = self.installer.create_plan(task.tools_to_install)
        if plan.requires_admin:
            await self.permission_manager.request_permission(
                operation="admin_install",
                description=f"Admin privileges required to install {len(plan.tools)} tools",
                level=PermissionLevel.ADMIN,
            )

        task.progress.progress_percent = 55
        await self._notify_progress()

    async def _phase_install(self, task: DeploymentTask) -> None:
        """Phase 4: Install tools."""
        if not task.tools_to_install:
            task.progress.progress_percent = 70
            return

        task.progress.status = TaskStatus.INSTALLING
        task.progress.current_step = f"Installing {len(task.tools_to_install)} tools"
        task.progress.progress_percent = 60
        await self._notify_progress()

        task.install_results = await self.installer.install_multiple(
            task.tools_to_install
        )

        task.progress.progress_percent = 80
        await self._notify_progress()

    async def _phase_models(self, task: DeploymentTask) -> None:
        """Phase 5: Pull AI models."""
        if not task.models_to_pull:
            task.progress.progress_percent = 90
            return

        task.progress.current_step = f"Pulling {len(task.models_to_pull)} models"
        task.progress.progress_percent = 85
        await self._notify_progress()

        for model_name in task.models_to_pull:
            try:
                await self.model_manager.pull_ollama_model(model_name)
            except Exception as e:
                task.progress.warnings.append(f"Failed to pull model {model_name}: {e}")

        task.progress.progress_percent = 90
        await self._notify_progress()

    async def _phase_report(self, task: DeploymentTask, start_time: datetime) -> None:
        """Phase 6: Generate deployment report."""
        task.progress.current_step = "Generating deployment report"
        task.progress.progress_percent = 95
        await self._notify_progress()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        task.report = self.reporting.create_report(
            scan_result=task.scan_result,
            analysis=task.analysis,
            install_results=task.install_results,
            duration_seconds=duration,
        )

        self.reporting.save_report(task.report)

        task.progress.progress_percent = 100
        await self._notify_progress()

    async def get_task_status(self, task_id: str) -> Optional[TaskProgress]:
        """Get the status of a task by ID."""
        state = await self.persistence.load_task_state(task_id)
        if state:
            return TaskProgress(**state.get("progress", {}))
        return None

    async def list_tasks(self) -> List[str]:
        """List all persisted task IDs."""
        return await self.persistence.list_tasks()

    def get_current_task(self) -> Optional[DeploymentTask]:
        """Get the currently running task."""
        return self._current_task
