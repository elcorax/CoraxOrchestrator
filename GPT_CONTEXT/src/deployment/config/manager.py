"""
Corax Orchestrator - Deployment Config Manager.

Manages deployment configuration loading, saving, and
resolution for AI infrastructure deployment.
"""

from typing import Dict, Any, Optional
import os
import json
import yaml

from src.deployment.config.base import (
    DeploymentConfig,
    DeploymentSettings,
    DeploymentMode,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class DeploymentConfigManager:
    """
    Manages deployment configuration.

    Handles loading from files, saving, and resolving
    configuration for deployment operations.
    """

    def __init__(self, config_dir: Optional[str] = None) -> None:
        self._config_dir = config_dir or self._get_default_config_dir()
        self._config: Optional[DeploymentConfig] = None

    def load(self, path: Optional[str] = None) -> DeploymentConfig:
        """
        Load deployment configuration from a file.

        Args:
            path: Path to config file (YAML or JSON)

        Returns:
            Loaded DeploymentConfig
        """
        file_path = path or os.path.join(self._config_dir, "deployment.yaml")

        if not os.path.exists(file_path):
            logger.info("No deployment config found, using defaults")
            self._config = DeploymentConfig()
            return self._config

        try:
            with open(file_path, "r") as f:
                if file_path.endswith(".json"):
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f) or {}

            self._config = self._from_dict(data)
            logger.info("Deployment config loaded", path=file_path)
            return self._config

        except Exception as e:
            logger.error("Failed to load deployment config", error=str(e))
            self._config = DeploymentConfig()
            return self._config

    def save(self, config: Optional[DeploymentConfig] = None, path: Optional[str] = None) -> str:
        """
        Save deployment configuration to a file.

        Args:
            config: Configuration to save (uses current if None)
            path: Output path (defaults to config dir)

        Returns:
            Path to saved file
        """
        config = config or self._config or DeploymentConfig()
        file_path = path or os.path.join(self._config_dir, "deployment.yaml")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        data = config.to_dict()

        with open(file_path, "w") as f:
            if file_path.endswith(".json"):
                json.dump(data, f, indent=2)
            else:
                yaml.dump(data, f, default_flow_style=False)

        logger.info("Deployment config saved", path=file_path)
        return file_path

    def get(self) -> DeploymentConfig:
        """Get the current deployment configuration."""
        if self._config is None:
            self._config = DeploymentConfig()
        return self._config

    def update(self, updates: Dict[str, Any]) -> DeploymentConfig:
        """
        Update deployment configuration with partial data.

        Args:
            updates: Dictionary of config updates

        Returns:
            Updated DeploymentConfig
        """
        config = self.get()

        if "profile" in updates:
            config.profile = updates["profile"]

        if "settings" in updates:
            settings = updates["settings"]
            if "mode" in settings:
                try:
                    config.settings.mode = DeploymentMode(settings["mode"])
                except ValueError:
                    pass
            if "auto_approve" in settings:
                config.settings.auto_approve = settings["auto_approve"]
            if "verify_install" in settings:
                config.settings.verify_install = settings["verify_install"]
            if "configure_integrations" in settings:
                config.settings.configure_integrations = settings["configure_integrations"]
            if "pull_models" in settings:
                config.settings.pull_models = settings["pull_models"]
            if "generate_report" in settings:
                config.settings.generate_report = settings["generate_report"]
            if "timeout" in settings:
                config.settings.timeout = settings["timeout"]
            if "retry_failed" in settings:
                config.settings.retry_failed = settings["retry_failed"]
            if "max_retries" in settings:
                config.settings.max_retries = settings["max_retries"]
            if "parallel_install" in settings:
                config.settings.parallel_install = settings["parallel_install"]
            if "max_parallel" in settings:
                config.settings.max_parallel = settings["max_parallel"]

        if "tool_overrides" in updates:
            config.tool_overrides.update(updates["tool_overrides"])

        if "model_overrides" in updates:
            config.model_overrides = updates["model_overrides"]

        if "environment" in updates:
            config.environment.update(updates["environment"])

        self._config = config
        return config

    def _from_dict(self, data: Dict[str, Any]) -> DeploymentConfig:
        """Convert dictionary to DeploymentConfig."""
        settings_data = data.get("settings", {})

        mode = DeploymentMode.SAFE
        if "mode" in settings_data:
            try:
                mode = DeploymentMode(settings_data["mode"])
            except ValueError:
                pass

        settings = DeploymentSettings(
            mode=mode,
            auto_approve=settings_data.get("auto_approve", False),
            verify_install=settings_data.get("verify_install", True),
            configure_integrations=settings_data.get("configure_integrations", True),
            pull_models=settings_data.get("pull_models", True),
            generate_report=settings_data.get("generate_report", True),
            timeout=settings_data.get("timeout", 3600),
            retry_failed=settings_data.get("retry_failed", True),
            max_retries=settings_data.get("max_retries", 3),
            parallel_install=settings_data.get("parallel_install", True),
            max_parallel=settings_data.get("max_parallel", 3),
        )

        return DeploymentConfig(
            profile=data.get("profile", "minimal_ai"),
            settings=settings,
            tool_overrides=data.get("tool_overrides", {}),
            model_overrides=data.get("model_overrides", []),
            environment=data.get("environment", {}),
            pre_install_hooks=data.get("pre_install_hooks", []),
            post_install_hooks=data.get("post_install_hooks", []),
        )

    def _get_default_config_dir(self) -> str:
        """Get default configuration directory."""
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config",
        )
