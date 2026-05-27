"""
Corax Orchestrator - Integration Manager.

Manages integrations between AI tools, configuring them to
work together as a cohesive AI development environment.
"""

from typing import Dict, Any, List, Optional
import asyncio

from src.deployment.integration.base import (
    IntegrationConfig,
    IntegrationResult,
    IntegrationType,
)
from src.deployment.installers.base import AIInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class IntegrationManager:
    """
    Manages integrations between AI tools.

    Handles configuring tools to work together, such as
    connecting Ollama as a backend for Open WebUI or
    Open Interpreter.
    """

    # Default integration configurations
    DEFAULT_INTEGRATIONS: Dict[IntegrationType, IntegrationConfig] = {
        IntegrationType.OLLAMA_WEBUI: IntegrationConfig(
            integration_type=IntegrationType.OLLAMA_WEBUI,
            source_tool="ollama",
            target_tool="open_webui",
            source_config={"host": "localhost", "port": 11434},
            target_config={"ollama_url": "http://localhost:11434"},
            description="Connect Ollama as the LLM backend for Open WebUI",
        ),
        IntegrationType.OLLAMA_INTERPRETER: IntegrationConfig(
            integration_type=IntegrationType.OLLAMA_INTERPRETER,
            source_tool="ollama",
            target_tool="open_interpreter",
            source_config={"host": "localhost", "port": 11434},
            target_config={
                "model": "ollama/llama3.1:8b",
                "api_base": "http://localhost:11434",
            },
            description="Connect Ollama as the LLM backend for Open Interpreter",
        ),
        IntegrationType.OLLAMA_ANYTHINGLLM: IntegrationConfig(
            integration_type=IntegrationType.OLLAMA_ANYTHINGLLM,
            source_tool="ollama",
            target_tool="anythingllm",
            source_config={"host": "localhost", "port": 11434},
            target_config={
                "llm_provider": "ollama",
                "ollama_endpoint": "http://localhost:11434",
            },
            description="Connect Ollama as the LLM backend for AnythingLLM",
        ),
        IntegrationType.LMSTUDIO_WEBUI: IntegrationConfig(
            integration_type=IntegrationType.LMSTUDIO_WEBUI,
            source_tool="lm_studio",
            target_tool="open_webui",
            source_config={"host": "localhost", "port": 1234},
            target_config={"ollama_url": "http://localhost:1234/v1"},
            description="Connect LM Studio as the LLM backend for Open WebUI",
        ),
        IntegrationType.LMSTUDIO_INTERPRETER: IntegrationConfig(
            integration_type=IntegrationType.LMSTUDIO_INTERPRETER,
            source_tool="lm_studio",
            target_tool="open_interpreter",
            source_config={"host": "localhost", "port": 1234},
            target_config={
                "model": "openai/lm-studio",
                "api_base": "http://localhost:1234/v1",
            },
            description="Connect LM Studio as the LLM backend for Open Interpreter",
        ),
    }

    def __init__(self) -> None:
        self._installers: Dict[str, AIInstallerBase] = {}

    def register_installer(self, installer: AIInstallerBase) -> None:
        """Register an installer for integration use."""
        self._installers[installer.tool_key] = installer

    async def apply_integration(
        self,
        integration_type: IntegrationType,
        custom_config: Optional[Dict[str, Any]] = None,
    ) -> IntegrationResult:
        """
        Apply a tool integration.

        Args:
            integration_type: Type of integration to apply
            custom_config: Optional custom configuration overrides

        Returns:
            IntegrationResult indicating success/failure
        """
        config = self.DEFAULT_INTEGRATIONS.get(integration_type)
        if not config:
            return IntegrationResult(
                integration_type=integration_type,
                success=False,
                message=f"Unknown integration type: {integration_type.value}",
            )

        # Apply custom config overrides
        if custom_config:
            if "source_config" in custom_config:
                config.source_config.update(custom_config["source_config"])
            if "target_config" in custom_config:
                config.target_config.update(custom_config["target_config"])

        logger.info(
            "Applying integration",
            integration_type=integration_type.value,
            source=config.source_tool,
            target=config.target_tool,
        )

        try:
            # Configure the target tool
            target_installer = self._installers.get(config.target_tool)
            if target_installer:
                result = await target_installer.configure(config.target_config)
                if result.status.value != "installed":
                    return IntegrationResult(
                        integration_type=integration_type,
                        success=False,
                        message=f"Failed to configure {config.target_tool}: {result.error}",
                        details={"configure_error": result.error},
                    )

            return IntegrationResult(
                integration_type=integration_type,
                success=True,
                message=f"Successfully integrated {config.source_tool} with {config.target_tool}",
                details={
                    "source": config.source_tool,
                    "target": config.target_tool,
                    "source_config": config.source_config,
                    "target_config": config.target_config,
                },
            )

        except Exception as e:
            logger.error(
                "Integration failed",
                integration_type=integration_type.value,
                error=str(e),
            )
            return IntegrationResult(
                integration_type=integration_type,
                success=False,
                message=f"Integration failed: {str(e)}",
                details={"error": str(e)},
            )

    async def apply_all(self) -> List[IntegrationResult]:
        """Apply all applicable integrations."""
        results = []
        for integration_type in IntegrationType:
            if integration_type == IntegrationType.CUSTOM:
                continue
            result = await self.apply_integration(integration_type)
            results.append(result)
        return results

    def get_available_integrations(self) -> List[Dict[str, Any]]:
        """Get list of available integrations."""
        integrations = []
        for integration_type, config in self.DEFAULT_INTEGRATIONS.items():
            integrations.append({
                "type": integration_type.value,
                "source": config.source_tool,
                "target": config.target_tool,
                "description": config.description,
            })
        return integrations
