"""
Corax Orchestrator - Deployment Config Base.

Defines deployment configuration models for the
AI infrastructure deployment system.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class DeploymentMode(Enum):
    """Deployment execution mode."""
    DRY_RUN = "dry_run"  # Simulate without making changes
    SAFE = "safe"  # Prompt before each action
    AUTOMATED = "automated"  # Full automated deployment
    RECOVERY = "recovery"  # Attempt to repair existing installation


@dataclass
class DeploymentSettings:
    """
    Settings for a deployment operation.

    Attributes:
        mode: Deployment execution mode
        auto_approve: Skip approval prompts
        verify_install: Verify installations after completion
        configure_integrations: Auto-configure tool integrations
        pull_models: Download recommended models
        generate_report: Generate deployment report
        timeout: Overall deployment timeout in seconds
        retry_failed: Retry failed installations
        max_retries: Maximum retry attempts per tool
        parallel_install: Install tools in parallel where possible
        max_parallel: Maximum parallel installations
    """
    mode: DeploymentMode = DeploymentMode.SAFE
    auto_approve: bool = False
    verify_install: bool = True
    configure_integrations: bool = True
    pull_models: bool = True
    generate_report: bool = True
    timeout: int = 3600
    retry_failed: bool = True
    max_retries: int = 3
    parallel_install: bool = True
    max_parallel: int = 3


@dataclass
class DeploymentConfig:
    """
    Complete deployment configuration.

    Attributes:
        profile: Deployment profile type or custom key
        settings: Deployment settings
        tool_overrides: Per-tool configuration overrides
        model_overrides: Model selection overrides
        environment: Environment variables to set
        pre_install_hooks: Scripts to run before installation
        post_install_hooks: Scripts to run after installation
    """
    profile: str = "minimal_ai"
    settings: DeploymentSettings = field(default_factory=DeploymentSettings)
    tool_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    model_overrides: List[str] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    pre_install_hooks: List[str] = field(default_factory=list)
    post_install_hooks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "settings": {
                "mode": self.settings.mode.value,
                "auto_approve": self.settings.auto_approve,
                "verify_install": self.settings.verify_install,
                "configure_integrations": self.settings.configure_integrations,
                "pull_models": self.settings.pull_models,
                "generate_report": self.settings.generate_report,
                "timeout": self.settings.timeout,
                "retry_failed": self.settings.retry_failed,
                "max_retries": self.settings.max_retries,
                "parallel_install": self.settings.parallel_install,
                "max_parallel": self.settings.max_parallel,
            },
            "tool_overrides": self.tool_overrides,
            "model_overrides": self.model_overrides,
            "environment": self.environment,
        }
