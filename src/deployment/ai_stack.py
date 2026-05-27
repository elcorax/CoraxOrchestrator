"""
Corax Orchestrator - AI Stack Deployment Orchestrator.

Coordinates the deployment of the complete AI infrastructure stack:
Ollama → LM Studio → Open WebUI → AnythingLLM → ComfyUI → Open Interpreter

Handles dependency ordering, parallel installation of independent tools,
model management, integration configuration, and health verification.
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
import asyncio
import time
import os

from src.core.logging import get_logger
from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus
from src.deployment.installers.ollama import OllamaInstaller
from src.deployment.installers.lm_studio import LMStudioInstaller
from src.deployment.installers.open_webui import OpenWebUIInstaller
from src.deployment.installers.anythingllm import AnythingLLMInstaller
from src.deployment.installers.comfyui import ComfyUIInstaller
from src.deployment.installers.open_interpreter import OpenInterpreterInstaller
from src.deployment.execution.executor import DeploymentExecutor
from src.deployment.execution.session import DeploymentSession
from src.deployment.unattended import UnattendedDeployment, UnattendedConfig, UnattendedResult
from src.deployment.validation import EnvironmentValidator
from src.deployment.windows_utils import WindowsUtils

logger = get_logger(__name__)


@dataclass
class AIStackResult:
    """Result of AI stack deployment."""
    success: bool = False
    tools: Dict[str, InstallResult] = field(default_factory=dict)
    models_pulled: List[str] = field(default_factory=list)
    integrations_configured: List[str] = field(default_factory=list)
    health_checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "tools": {k: v.to_dict() for k, v in self.tools.items()},
            "models_pulled": self.models_pulled,
            "integrations_configured": self.integrations_configured,
            "health_checks": self.health_checks,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_seconds": round(self.duration_seconds, 1),
        }


class AIStackDeployer:
    """
    Coordinates complete AI infrastructure stack deployment.

    Deployment order:
    1. Ollama (LLM runtime - foundation)
    2. LM Studio (GUI LLM runtime - parallel with Ollama)
    3. Open WebUI (web UI - depends on Ollama)
    4. AnythingLLM (RAG system - parallel with Open WebUI)
    5. ComfyUI (image generation - depends on git/python)
    6. Open Interpreter (AI agent - depends on Ollama)
    7. Model pulling (after Ollama is ready)
    8. Integration configuration
    9. Health verification
    """

    # Dependency graph for AI tools
    DEPENDENCY_GRAPH: Dict[str, List[str]] = {
        "ollama": [],
        "lm_studio": [],
        "open_webui": ["ollama"],
        "anythingllm": [],
        "comfyui": ["git", "python"],
        "open_interpreter": ["ollama"],
    }

    # Tools that can be installed in parallel (no dependencies between them)
    PARALLEL_GROUPS: List[List[str]] = [
        ["ollama", "lm_studio", "anythingllm"],
        ["open_webui", "comfyui", "open_interpreter"],
    ]

    # Default models to pull for each tool
    DEFAULT_MODELS: Dict[str, List[str]] = {
        "ollama": ["llama3.2:1b", "nomic-embed-text"],
        "lm_studio": [],
        "open_webui": [],
        "anythingllm": [],
        "comfyui": [],
        "open_interpreter": [],
    }

    def __init__(
        self,
        data_dir: str = "data",
        unattended_config: Optional[UnattendedConfig] = None,
    ) -> None:
        self._data_dir = data_dir
        self._installers: Dict[str, AIInstallerBase] = {}
        self._results: Dict[str, InstallResult] = {}
        self._win_utils = WindowsUtils()
        self._validator = EnvironmentValidator()
        self._unattended_config = unattended_config or UnattendedConfig()

        # Register all AI installers
        self._register_installers()

    def _register_installers(self) -> None:
        """Register all AI tool installers."""
        installers = [
            OllamaInstaller(),
            LMStudioInstaller(),
            OpenWebUIInstaller(),
            AnythingLLMInstaller(),
            ComfyUIInstaller(),
            OpenInterpreterInstaller(),
        ]
        for installer in installers:
            self._installers[installer.tool_key] = installer
            logger.debug("Registered installer", tool=installer.tool_key)

    @property
    def installers(self) -> Dict[str, AIInstallerBase]:
        return dict(self._installers)

    @property
    def results(self) -> Dict[str, InstallResult]:
        return dict(self._results)

    async def deploy_all(
        self,
        pull_models: bool = True,
        configure_integrations: bool = True,
        verify_health: bool = True,
        unattended: bool = False,
    ) -> AIStackResult:
        """
        Deploy the complete AI stack.

        Args:
            pull_models: Whether to pull default models
            configure_integrations: Whether to configure tool integrations
            verify_health: Whether to run health verification
            unattended: Use unattended mode with watchdog and retry

        Returns:
            AIStackResult with complete deployment results
        """
        result = AIStackResult()
        start_time = time.time()

        logger.info("Starting AI stack deployment")

        try:
            if unattended:
                return await self._deploy_unattended(
                    pull_models, configure_integrations, verify_health
                )

            # Phase 1: Detect all tools
            await self._phase_detection(result)

            # Phase 2: Install tools in dependency order
            await self._phase_installation(result)

            # Phase 3: Pull models
            if pull_models:
                await self._phase_model_pulling(result)

            # Phase 4: Configure integrations
            if configure_integrations:
                await self._phase_integrations(result)

            # Phase 5: Health verification
            if verify_health:
                await self._phase_health_verification(result)

            # Determine overall success
            installed_count = sum(
                1 for r in self._results.values()
                if r.status == InstallStatus.INSTALLED
            )
            total_count = len(self._installers)
            result.success = installed_count >= total_count * 0.5  # 50%+ success

            if installed_count < total_count:
                result.warnings.append(
                    f"Installed {installed_count}/{total_count} tools"
                )

        except Exception as e:
            error_msg = f"AI stack deployment failed: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            result.success = False
        finally:
            result.duration_seconds = time.time() - start_time

        return result

    async def _deploy_unattended(
        self,
        pull_models: bool,
        configure_integrations: bool,
        verify_health: bool,
    ) -> AIStackResult:
        """Deploy using unattended mode."""
        session = DeploymentSession(data_dir=self._data_dir)
        unattended = UnattendedDeployment(
            config=self._unattended_config,
            session=session,
            data_dir=self._data_dir,
        )

        # Register all installers with the session
        for key, installer in self._installers.items():
            session.executor.register_installer(installer)

        # Run unattended deployment
        tool_keys = list(self._installers.keys())
        unattended_result = await unattended.run(
            tool_keys=tool_keys,
            profile_name="ai_stack",
            skip_existing=True,
            parallel=True,
        )

        # Convert to AIStackResult
        result = AIStackResult()
        result.success = unattended_result.success
        result.duration_seconds = unattended_result.duration_seconds

        if unattended_result.session_result:
            for tool_key in unattended_result.session_result.tools_installed:
                installer = self._installers.get(tool_key)
                if installer:
                    detect_result = await installer.detect()
                    self._results[tool_key] = detect_result
                    result.tools[tool_key] = detect_result

            for tool_key in unattended_result.session_result.tools_failed:
                result.errors.append(f"Failed to install {tool_key}")

        result.warnings.extend(unattended_result.warnings)
        result.errors.extend(unattended_result.errors)

        return result

    async def _phase_detection(self, result: AIStackResult) -> None:
        """Phase 1: Detect all AI tools."""
        logger.info("Phase 1: Detecting AI tools")

        for key, installer in self._installers.items():
            try:
                detect_result = await installer.detect()
                self._results[key] = detect_result
                result.tools[key] = detect_result
                logger.info(
                    "Tool detection",
                    tool=key,
                    status=detect_result.status.value,
                    version=detect_result.version,
                )
            except Exception as e:
                logger.error("Detection failed", tool=key, error=str(e))
                self._results[key] = InstallResult(
                    tool_name=installer.tool_name,
                    status=InstallStatus.FAILED,
                    error=str(e),
                )

    async def _phase_installation(self, result: AIStackResult) -> None:
        """Phase 2: Install tools in dependency order."""
        logger.info("Phase 2: Installing AI tools")

        for group_idx, group in enumerate(self.PARALLEL_GROUPS):
            logger.info(
                f"Installing group {group_idx + 1}/{len(self.PARALLEL_GROUPS)}",
                tools=group,
            )

            tasks = []
            for tool_key in group:
                installer = self._installers.get(tool_key)
                if not installer:
                    continue

                # Check if already installed
                existing = self._results.get(tool_key)
                if existing and existing.status == InstallStatus.INSTALLED:
                    logger.info("Already installed, skipping", tool=tool_key)
                    continue

                # Check dependencies
                deps = self.DEPENDENCY_GRAPH.get(tool_key, [])
                deps_met = all(
                    dep in self._installers or dep in self._results
                    for dep in deps
                )
                if not deps_met:
                    logger.warning(
                        "Dependencies not met, skipping",
                        tool=tool_key,
                        dependencies=deps,
                    )
                    result.warnings.append(
                        f"Skipped {tool_key}: unmet dependencies {deps}"
                    )
                    continue

                tasks.append(self._install_tool(tool_key, installer, result))

            if tasks:
                await asyncio.gather(*tasks)

    async def _install_tool(
        self,
        tool_key: str,
        installer: AIInstallerBase,
        result: AIStackResult,
    ) -> None:
        """Install a single tool with retry."""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                install_result = await installer.install()
                self._results[tool_key] = install_result
                result.tools[tool_key] = install_result

                if install_result.status == InstallStatus.INSTALLED:
                    logger.info("Installation succeeded", tool=tool_key)
                    return
                elif install_result.status == InstallStatus.FAILED:
                    if attempt < max_retries:
                        logger.warning(
                            "Installation failed, retrying",
                            tool=tool_key,
                            attempt=attempt + 1,
                            error=install_result.error,
                        )
                        await asyncio.sleep(5 * (attempt + 1))
                    else:
                        logger.error(
                            "Installation failed after retries",
                            tool=tool_key,
                            error=install_result.error,
                        )
                        result.errors.append(
                            f"Failed to install {tool_key}: {install_result.error}"
                        )
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        "Installation error, retrying",
                        tool=tool_key,
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    logger.error(
                        "Installation error after retries",
                        tool=tool_key,
                        error=str(e),
                    )
                    result.errors.append(f"Failed to install {tool_key}: {e}")

    async def _phase_model_pulling(self, result: AIStackResult) -> None:
        """Phase 3: Pull default models."""
        logger.info("Phase 3: Pulling AI models")

        for tool_key, models in self.DEFAULT_MODELS.items():
            if not models:
                continue

            tool_result = self._results.get(tool_key)
            if not tool_result or tool_result.status != InstallStatus.INSTALLED:
                logger.info("Tool not installed, skipping model pull", tool=tool_key)
                continue

            for model_id in models:
                try:
                    logger.info("Pulling model", tool=tool_key, model=model_id)
                    # Use Ollama CLI to pull models
                    if tool_key == "ollama":
                        from src.deployment.installers.base import AIInstallerBase
                        # Create a temporary base for running commands
                        code, stdout, stderr = await asyncio.create_subprocess_exec(
                            "ollama", "pull", model_id,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        # Actually use _run_command from the installer
                        installer = self._installers.get(tool_key)
                        if installer:
                            code, stdout, stderr = await installer._run_command(
                                ["ollama", "pull", model_id],
                                timeout=600,
                            )
                            if code == 0:
                                result.models_pulled.append(model_id)
                                logger.info("Model pulled", model=model_id)
                            else:
                                result.warnings.append(
                                    f"Failed to pull model {model_id}: {stderr[:200]}"
                                )
                except Exception as e:
                    result.warnings.append(
                        f"Failed to pull model {model_id}: {e}"
                    )

    async def _phase_integrations(self, result: AIStackResult) -> None:
        """Phase 4: Configure tool integrations."""
        logger.info("Phase 4: Configuring integrations")

        # Configure Ollama as backend for Open WebUI
        ollama_result = self._results.get("ollama")
        if ollama_result and ollama_result.status == InstallStatus.INSTALLED:
            open_webui = self._installers.get("open_webui")
            if open_webui:
                try:
                    config_result = await open_webui.configure({
                        "ollama_url": "http://localhost:11434",
                    })
                    if config_result.status == InstallStatus.INSTALLED:
                        result.integrations_configured.append("open_webui->ollama")
                except Exception as e:
                    result.warnings.append(f"Failed to configure Open WebUI: {e}")

        # Configure Ollama as backend for Open Interpreter
        open_interpreter = self._installers.get("open_interpreter")
        if open_interpreter:
            try:
                config_result = await open_interpreter.configure({
                    "model": "ollama/llama3.2",
                    "api_base": "http://localhost:11434",
                })
                if config_result.status == InstallStatus.INSTALLED:
                    result.integrations_configured.append("open_interpreter->ollama")
            except Exception as e:
                result.warnings.append(f"Failed to configure Open Interpreter: {e}")

        # Configure AnythingLLM with Ollama backend
        anythingllm = self._installers.get("anythingllm")
        if anythingllm:
            try:
                config_result = await anythingllm.configure({
                    "llm_provider": "ollama",
                    "ollama_endpoint": "http://localhost:11434",
                })
                if config_result.status == InstallStatus.INSTALLED:
                    result.integrations_configured.append("anythingllm->ollama")
            except Exception as e:
                result.warnings.append(f"Failed to configure AnythingLLM: {e}")

    async def _phase_health_verification(self, result: AIStackResult) -> None:
        """Phase 5: Verify deployment health."""
        logger.info("Phase 5: Health verification")

        for tool_key, installer in self._installers.items():
            tool_result = self._results.get(tool_key)
            if not tool_result or tool_result.status != InstallStatus.INSTALLED:
                result.health_checks[tool_key] = False
                continue

            try:
                verify_result = await installer.verify()
                is_healthy = verify_result.status == InstallStatus.INSTALLED
                result.health_checks[tool_key] = is_healthy

                if not is_healthy:
                    result.warnings.append(
                        f"{tool_key} installed but health check failed: "
                        f"{verify_result.error}"
                    )
            except Exception as e:
                result.health_checks[tool_key] = False
                result.warnings.append(
                    f"Health check failed for {tool_key}: {e}"
                )

    async def deploy_single(
        self,
        tool_key: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> InstallResult:
        """
        Deploy a single AI tool.

        Args:
            tool_key: Tool identifier (e.g., "ollama", "lm_studio")
            config: Optional installation configuration

        Returns:
            InstallResult for the tool
        """
        installer = self._installers.get(tool_key)
        if not installer:
            return InstallResult(
                tool_name=tool_key,
                status=InstallStatus.FAILED,
                error=f"Unknown tool: {tool_key}",
            )

        logger.info("Deploying single tool", tool=tool_key)

        # Detect first
        detect_result = await installer.detect()
        if detect_result.status == InstallStatus.INSTALLED:
            logger.info("Already installed", tool=tool_key)
            return detect_result

        # Install
        install_result = await installer.install(config)
        self._results[tool_key] = install_result

        return install_result

    def get_deployment_summary(self) -> Dict[str, Any]:
        """Get a summary of the current deployment state."""
        summary = {
            "total_tools": len(self._installers),
            "installed": 0,
            "failed": 0,
            "not_installed": 0,
            "tools": {},
        }

        for key, result in self._results.items():
            status = result.status.value
            summary["tools"][key] = {
                "status": status,
                "version": result.version,
                "error": result.error,
            }

            if result.status == InstallStatus.INSTALLED:
                summary["installed"] += 1
            elif result.status == InstallStatus.FAILED:
                summary["failed"] += 1
            else:
                summary["not_installed"] += 1

        return summary
