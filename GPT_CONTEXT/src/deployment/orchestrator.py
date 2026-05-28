"""
Corax Orchestrator - Deployment Orchestrator.

The main deployment orchestrator that coordinates the entire
AI infrastructure deployment process from scanning through
installation, verification, and reporting.
"""

from typing import Dict, Any, List, Optional
import asyncio
import time
import os
import sys
from pathlib import Path

from src.core.logging import get_logger
from src.core.exceptions import InstallationError
from src.deployment.config.base import (
    DeploymentConfig,
    DeploymentSettings,
    DeploymentMode,
)
from src.deployment.config.manager import DeploymentConfigManager
from src.deployment.profiles.base import (
    DeploymentProfile,
    DeploymentProfileType,
    ProfileConfig,
)
from src.deployment.profiles.manager import ProfileManager
from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus
from src.deployment.models.registry import ModelRegistry
from src.deployment.models.recommender import ModelRecommender
from src.deployment.verification.health import HealthChecker
from src.deployment.integration.manager import IntegrationManager
from src.deployment.repair.engine import RepairEngine
from src.modules.system_scanner import SystemScanner
from src.modules.environment_analyzer import EnvironmentAnalyzer
from src.modules.tool_registry import ToolRegistry
from src.modules.installer_engine import InstallerEngine
from src.modules.model_manager import ModelManager
from src.modules.permission_manager import PermissionManager
from src.modules.self_healing import SelfHealingEngine
from src.modules.state_persistence import StatePersistence
from src.modules.reporting import ReportingEngine
from src.modules.task_orchestrator import TaskOrchestrator
from src.runtime.state_bus import state_bus, EventType, EventPriority
from src.deployment.restore.windows_restore import WindowsRestorePoint, windows_restore

logger = get_logger(__name__)


class DeploymentOrchestrator:
    """
    Main deployment orchestrator for AI infrastructure.

    Coordinates the entire deployment lifecycle:
    1. Configuration loading
    2. System scanning
    3. Environment analysis
    4. Profile resolution
    5. Tool installation
    6. Model management
    7. Integration configuration
    8. Health verification
    9. Report generation
    """

    def __init__(self) -> None:
        # Core systems
        self.config_manager = DeploymentConfigManager()
        self.profile_manager = ProfileManager()
        self.system_scanner = SystemScanner()
        self.environment_analyzer = EnvironmentAnalyzer()
        self.tool_registry = ToolRegistry()
        self.installer_engine = InstallerEngine()
        self.model_manager = ModelManager()
        self.permission_manager = PermissionManager()
        self.self_healing = SelfHealingEngine()
        self.state_persistence = StatePersistence()
        self.reporting = ReportingEngine()
        self.task_orchestrator = TaskOrchestrator()

        # Deployment-specific systems
        self.model_registry = ModelRegistry()
        self.model_recommender = ModelRecommender()
        self.health_checker = HealthChecker()
        self.integration_manager = IntegrationManager()
        self.repair_engine = RepairEngine()

        # State
        self._installers: Dict[str, AIInstallerBase] = {}
        self._results: Dict[str, Any] = {}
        self._config: Optional[DeploymentConfig] = None

    def register_installer(self, installer: AIInstallerBase) -> None:
        """Register an AI tool installer."""
        key = installer.tool_key
        self._installers[key] = installer
        self.installer_engine.register_installer(installer)
        self.health_checker.add_check(
            lambda inst=installer: self.health_checker.check_tool(inst)
        )
        self.integration_manager.register_installer(installer)
        self.repair_engine.register_installer(installer)
        logger.info("Installer registered", tool=key)

    async def deploy(
        self,
        profile_type: Optional[DeploymentProfileType] = None,
        custom_profile_key: Optional[str] = None,
        intent_query: Optional[str] = None,
        config_updates: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full deployment.

        Args:
            profile_type: Built-in profile type
            custom_profile_key: Custom profile key
            intent_query: Natural language deployment request
            config_updates: Configuration overrides

        Returns:
            Deployment results dictionary
        """
        start_time = time.time()
        self._results = {"started_at": time.time(), "phases": {}}

        # Phase 0: Restore Point (mandatory safeguard)
        self._create_pre_deployment_restore_point()

        try:
            # Phase 1: Configuration
            await self._phase_configuration(config_updates)

            # Phase 2: Profile Resolution
            profile = await self._phase_profile_resolution(
                profile_type, custom_profile_key, intent_query
            )
            if not profile:
                return self._finalize(start_time, "failed", "No deployment profile resolved")

            # Phase 3: System Scan
            await self._phase_system_scan()

            # Phase 4: Environment Analysis
            await self._phase_environment_analysis()

            # Phase 5: Permission Check
            await self._phase_permission_check()

            # Phase 6: Tool Installation
            await self._phase_tool_installation(profile)

            # Phase 7: Model Management
            await self._phase_model_management(profile)

            # Phase 8: Integration Configuration
            await self._phase_integration_configuration()

            # Phase 9: Health Verification
            await self._phase_health_verification()

            # Phase 10: Report Generation
            await self._phase_report_generation()

            # Phase 11: State Persistence
            await self._phase_state_persistence()

            return self._finalize(start_time, "completed", "Deployment completed successfully")

        except Exception as e:
            logger.error("Deployment failed", error=str(e))
            self._results.setdefault("errors", []).append(str(e))

            # Attempt self-healing
            await self._attempt_recovery()

            return self._finalize(start_time, "failed", f"Deployment failed: {str(e)}")

    async def _phase_configuration(
        self, config_updates: Optional[Dict[str, Any]] = None
    ) -> None:
        """Phase 1: Load and apply configuration."""
        logger.info("Phase 1/11: Configuration")

        self._config = self.config_manager.load()

        if config_updates:
            self._config = self.config_manager.update(config_updates)

        self._results["phases"]["configuration"] = {
            "status": "completed",
            "profile": self._config.profile,
            "mode": self._config.settings.mode.value,
        }

    async def _phase_profile_resolution(
        self,
        profile_type: Optional[DeploymentProfileType] = None,
        custom_key: Optional[str] = None,
        intent_query: Optional[str] = None,
    ) -> Optional[ProfileConfig]:
        """Phase 2: Resolve deployment profile."""
        logger.info("Phase 2/11: Profile Resolution")

        profile = self.profile_manager.resolve_profile(
            profile_type=profile_type,
            custom_key=custom_key,
            intent_query=intent_query,
        )

        if profile:
            self._results["phases"]["profile"] = {
                "status": "completed",
                "name": profile.name,
                "tools": profile.tools,
                "models": profile.models,
            }
        else:
            self._results["phases"]["profile"] = {
                "status": "failed",
                "message": "No profile resolved",
            }

        return profile

    async def _phase_system_scan(self) -> None:
        """Phase 3: Scan system hardware and software."""
        logger.info("Phase 3/11: System Scan")

        scan_result = await self.system_scanner.scan()
        self._results["phases"]["system_scan"] = {
            "status": "completed",
            "os": scan_result.get("os", {}),
            "hardware": scan_result.get("hardware", {}),
        }

    async def _phase_environment_analysis(self) -> None:
        """Phase 4: Analyze development environment."""
        logger.info("Phase 4/11: Environment Analysis")

        analysis = await self.environment_analyzer.analyze()
        self._results["phases"]["environment_analysis"] = {
            "status": "completed",
            "python": analysis.get("python", {}),
            "tools": analysis.get("tools", {}),
            "missing": analysis.get("missing", []),
        }

    async def _phase_permission_check(self) -> None:
        """Phase 5: Check and request permissions."""
        logger.info("Phase 5/11: Permission Check")

        config = self._config or DeploymentConfig()
        if config.settings.mode == DeploymentMode.DRY_RUN:
            self._results["phases"]["permissions"] = {
                "status": "skipped",
                "reason": "Dry run mode",
            }
            return

        permissions = await self.permission_manager.check_all()
        self._results["phases"]["permissions"] = {
            "status": "completed",
            "permissions": permissions,
        }

    async def _phase_tool_installation(self, profile: ProfileConfig) -> None:
        """Phase 6: Install AI tools."""
        logger.info("Phase 6/11: Tool Installation")

        config = self._config or DeploymentConfig()
        install_results = {}

        for tool_key in profile.tools:
            installer = self._installers.get(tool_key)
            if not installer:
                logger.warning("No installer for tool", tool=tool_key)
                install_results[tool_key] = {"status": "skipped", "reason": "No installer"}
                continue

            # Apply tool overrides
            if tool_key in config.tool_overrides:
                for k, v in config.tool_overrides[tool_key].items():
                    if hasattr(installer, k):
                        setattr(installer, k, v)

            if config.settings.mode == DeploymentMode.DRY_RUN:
                install_results[tool_key] = {"status": "simulated"}
                continue

            try:
                result = await installer.install()
                install_results[tool_key] = {
                    "status": result.status.value,
                    "version": result.version,
                    "error": result.error,
                }
            except Exception as e:
                install_results[tool_key] = {"status": "failed", "error": str(e)}

        self._results["phases"]["installation"] = {
            "status": "completed",
            "results": install_results,
        }

    async def _phase_model_management(self, profile: ProfileConfig) -> None:
        """Phase 7: Download and manage AI models."""
        logger.info("Phase 7/11: Model Management")

        config = self._config or DeploymentConfig()
        if not config.settings.pull_models:
            self._results["phases"]["models"] = {
                "status": "skipped",
                "reason": "Model pulling disabled",
            }
            return

        models = profile.models
        if config.model_overrides:
            models = config.model_overrides

        model_results = {}
        for model_id in models:
            try:
                result = await self.model_manager.pull_model(model_id)
                model_results[model_id] = {
                    "status": result.get("status", "unknown"),
                    "size": result.get("size", "unknown"),
                }
            except Exception as e:
                model_results[model_id] = {"status": "failed", "error": str(e)}

        self._results["phases"]["models"] = {
            "status": "completed",
            "results": model_results,
        }

    async def _phase_integration_configuration(self) -> None:
        """Phase 8: Configure tool integrations."""
        logger.info("Phase 8/11: Integration Configuration")

        config = self._config or DeploymentConfig()
        if not config.settings.configure_integrations:
            self._results["phases"]["integrations"] = {
                "status": "skipped",
                "reason": "Integration configuration disabled",
            }
            return

        integration_results = await self.integration_manager.apply_all()
        self._results["phases"]["integrations"] = {
            "status": "completed",
            "results": [r.to_dict() for r in integration_results],
        }

    async def _phase_health_verification(self) -> None:
        """Phase 9: Verify deployment health."""
        logger.info("Phase 9/11: Health Verification")

        config = self._config or DeploymentConfig()
        if not config.settings.verify_install:
            self._results["phases"]["verification"] = {
                "status": "skipped",
                "reason": "Verification disabled",
            }
            return

        # Add standard checks
        self.health_checker.add_check(
            lambda: self.health_checker.check_system_resources()
        )
        self.health_checker.add_check(
            lambda: self.health_checker.check_python_environment()
        )
        self.health_checker.add_check(
            lambda: self.health_checker.check_docker()
        )

        results = await self.health_checker.run_all()
        summary = self.health_checker.get_summary(results)

        self._results["phases"]["verification"] = {
            "status": "completed",
            "summary": summary,
            "checks": [r.to_dict() for r in results],
        }

    async def _phase_report_generation(self) -> None:
        """Phase 10: Generate deployment report."""
        logger.info("Phase 10/11: Report Generation")

        config = self._config or DeploymentConfig()
        if not config.settings.generate_report:
            self._results["phases"]["report"] = {
                "status": "skipped",
                "reason": "Report generation disabled",
            }
            return

        report = await self.reporting.generate_report(self._results)
        self._results["phases"]["report"] = {
            "status": "completed",
            "report_path": report.get("path"),
            "report_id": report.get("id"),
        }

    async def _phase_state_persistence(self) -> None:
        """Phase 11: Persist deployment state."""
        logger.info("Phase 11/11: State Persistence")

        await self.state_persistence.save("deployment_results", self._results)
        self._results["phases"]["persistence"] = {"status": "completed"}

    def _create_pre_deployment_restore_point(self) -> None:
        """Create a Windows System Restore Point before deployment."""
        try:
            if sys.platform == "win32":
                result = windows_restore.create_before_install(
                    "AI Workstation Deployment"
                )
                if result.success:
                    logger.info(
                        "Pre-deployment restore point created",
                        description=result.description,
                    )
                else:
                    logger.warning(
                        "Pre-deployment restore point not available",
                        reason=result.error,
                    )
            else:
                logger.info(
                    "Restore point skipped (non-Windows platform)",
                    platform=sys.platform,
                )
        except Exception as e:
            logger.warning(f"Restore point creation attempt failed: {e}")

    async def _attempt_recovery(self) -> None:
        """Attempt recovery from deployment failures."""
        logger.info("Attempting deployment recovery")

        try:
            repair_results = await self.repair_engine.run_all()
            self._results["recovery"] = {
                "attempted": True,
                "results": [r.to_dict() for r in repair_results],
            }
        except Exception as e:
            logger.error("Recovery failed", error=str(e))
            self._results["recovery"] = {
                "attempted": True,
                "error": str(e),
            }

    def _finalize(
        self, start_time: float, status: str, message: str
    ) -> Dict[str, Any]:
        """Finalize deployment results."""
        duration = round(time.time() - start_time, 2)

        self._results["status"] = status
        self._results["message"] = message
        self._results["duration_seconds"] = duration
        self._results["completed_at"] = time.time()

        logger.info(
            "Deployment finalized",
            status=status,
            duration=duration,
        )

        return self._results

    # ─── Single Tool Installation (called by autonomous deployer) ───

    async def install_tool(self, tool_name: str, attempt: int = 1) -> InstallResult:
        """
        Install a single tool with restore point safeguard, state bus events,
        and real installer execution.

        This is the PRIMARY entry point called by the AutonomousDeploymentEngine.

        Args:
            tool_name: Key of the tool to install
            attempt: Current retry attempt number

        Returns:
            InstallResult with status, version, error details
        """
        logger.info("Installing tool", tool=tool_name, attempt=attempt)

        # Create per-tool restore point BEFORE installation
        self._create_tool_restore_point(tool_name)

        # Publish deployment progress event
        state_bus.publish_sync(
            EventType.DEPLOYMENT_PROGRESS,
            payload={
                "tool_name": tool_name,
                "progress_percent": min(attempt * 20, 90),
                "current_step": f"Installing {tool_name} (attempt {attempt})",
                "retry_count": attempt - 1,
            },
            source="orchestrator",
            priority=EventPriority.NORMAL,
        )

        # Find installer
        installer = self._installers.get(tool_name)
        if not installer:
            result = InstallResult(
                tool_name=tool_name,
                status=InstallStatus.BLOCKED,
                error=f"No installer registered for {tool_name}",
            )
            logger.warning("No installer available", tool=tool_name)
            state_bus.publish_sync(
                EventType.DEPLOYMENT_TOOL_FAILED,
                payload={"tool_name": tool_name, "error": result.error},
                source="orchestrator",
            )
            return result

        # Execute real installation
        try:
            start_ts = time.time()
            install_result = await installer.install()
            duration_ms = (time.time() - start_ts) * 1000
            install_result.duration_ms = duration_ms
            install_result.retry_attempts = attempt - 1

            logger.info(
                "Tool install result",
                tool=tool_name,
                status=install_result.status.value,
                duration_ms=round(duration_ms, 1),
            )

            # Publish completion event
            event_type = (
                EventType.DEPLOYMENT_TOOL_COMPLETED
                if install_result.status == InstallStatus.INSTALLED
                else EventType.DEPLOYMENT_TOOL_FAILED
            )
            state_bus.publish_sync(
                event_type,
                payload={
                    "tool_name": tool_name,
                    "status": install_result.status.value,
                    "version": install_result.version,
                    "error": install_result.error,
                    "duration_ms": duration_ms,
                },
                source="orchestrator",
            )

            return install_result

        except Exception as e:
            logger.error("Tool install exception", tool=tool_name, error=str(e))
            result = InstallResult(
                tool_name=tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )
            state_bus.publish_sync(
                EventType.DEPLOYMENT_TOOL_FAILED,
                payload={"tool_name": tool_name, "error": str(e)},
                source="orchestrator",
            )
            return result

    def _create_tool_restore_point(self, tool_name: str) -> None:
        """Create Windows Restore Point for a single tool installation."""
        try:
            if sys.platform == "win32":
                result = windows_restore.create_before_install(tool_name)
                if result.success:
                    logger.debug("Tool restore point created", tool=tool_name)
                else:
                    logger.debug(
                        "Tool restore point skipped",
                        tool=tool_name,
                        reason=result.error,
                    )
        except Exception as e:
            logger.debug(f"Tool restore point failed: {e}")

    async def pull_model(self, model_name: str) -> Dict[str, Any]:
        """
        Pull an AI model with state bus event propagation.

        Args:
            model_name: Model identifier to pull

        Returns:
            Dict with status and size information
        """
        logger.info("Pulling model", model=model_name)

        state_bus.publish_sync(
            EventType.MODEL_PROGRESS,
            payload={"model_name": model_name, "progress": 0},
            source="orchestrator",
        )

        try:
            result = await self.model_manager.pull_model(model_name)
            state_bus.publish_sync(
                EventType.MODEL_COMPLETED,
                payload={
                    "model_name": model_name,
                    "status": result.get("status", "unknown"),
                },
                source="orchestrator",
            )
            return result
        except Exception as e:
            logger.error("Model pull failed", model=model_name, error=str(e))
            state_bus.publish_sync(
                EventType.DEPLOYMENT_TOOL_FAILED,
                payload={"model_name": model_name, "error": str(e)},
                source="orchestrator",
            )
            return {"status": "failed", "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get current deployment status."""
        return {
            "has_config": self._config is not None,
            "registered_installers": list(self._installers.keys()),
            "results_available": bool(self._results),
            "current_status": self._results.get("status", "not_started"),
        }
