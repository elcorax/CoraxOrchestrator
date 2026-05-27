"""
Corax Orchestrator - Profile Manager.

Manages deployment profiles including loading, saving, and
resolving profile configurations for deployment.
"""

from typing import Dict, Any, List, Optional
import json
import os
import yaml

from src.deployment.profiles.base import (
    DeploymentProfile,
    DeploymentProfileType,
    ProfileConfig,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class ProfileManager:
    """
    Manages deployment profiles.

    Handles profile loading, saving, custom profile creation,
    and profile resolution for deployment orchestration.
    """

    def __init__(self, profiles_dir: Optional[str] = None) -> None:
        self._profiles_dir = profiles_dir or self._get_default_profiles_dir()
        self._custom_profiles: Dict[str, ProfileConfig] = {}

    def get_profile(self, profile_type: DeploymentProfileType) -> DeploymentProfile:
        """Get a built-in profile."""
        return DeploymentProfile(profile_type)

    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Get all available profiles (built-in + custom)."""
        profiles = [p.to_dict() for p in DeploymentProfile.get_all()]

        for name, config in self._custom_profiles.items():
            profiles.append({
                "type": "custom",
                "name": config.name,
                "description": config.description,
                "tools": config.tools,
                "models": config.models,
                "install_configs": config.install_configs,
                "requires_docker": config.requires_docker,
                "requires_gpu": config.requires_gpu,
                "estimated_disk_gb": config.estimated_disk_gb,
                "custom_key": name,
            })

        return profiles

    def create_custom_profile(
        self,
        name: str,
        description: str,
        tools: List[str],
        models: Optional[List[str]] = None,
        install_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """
        Create a custom deployment profile.

        Args:
            name: Display name
            description: Profile description
            tools: List of tool keys to install
            models: List of model IDs to pull
            install_configs: Per-tool installation configs

        Returns:
            Profile key for reference
        """
        key = name.lower().replace(" ", "_")

        self._custom_profiles[key] = ProfileConfig(
            name=name,
            description=description,
            tools=tools,
            models=models or [],
            install_configs=install_configs or {},
        )

        logger.info("Custom profile created", key=key, name=name)
        return key

    def resolve_profile(
        self,
        profile_type: Optional[DeploymentProfileType] = None,
        custom_key: Optional[str] = None,
        intent_query: Optional[str] = None,
    ) -> Optional[ProfileConfig]:
        """
        Resolve a profile from various input types.

        Priority: profile_type > custom_key > intent_query

        Args:
            profile_type: Built-in profile type
            custom_key: Custom profile key
            intent_query: Natural language query

        Returns:
            Resolved ProfileConfig or None
        """
        if profile_type:
            return DeploymentProfile(profile_type).config

        if custom_key and custom_key in self._custom_profiles:
            return self._custom_profiles[custom_key]

        if intent_query:
            profile = DeploymentProfile.match_intent(intent_query)
            if profile:
                return profile.config

        return None

    def save_profiles(self) -> None:
        """Save custom profiles to disk."""
        os.makedirs(self._profiles_dir, exist_ok=True)
        path = os.path.join(self._profiles_dir, "custom_profiles.yaml")

        data = {}
        for key, config in self._custom_profiles.items():
            data[key] = {
                "name": config.name,
                "description": config.description,
                "tools": config.tools,
                "models": config.models,
                "install_configs": config.install_configs,
                "requires_docker": config.requires_docker,
                "requires_gpu": config.requires_gpu,
                "estimated_disk_gb": config.estimated_disk_gb,
            }

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        logger.info("Custom profiles saved", count=len(data))

    def load_profiles(self) -> None:
        """Load custom profiles from disk."""
        path = os.path.join(self._profiles_dir, "custom_profiles.yaml")
        if not os.path.exists(path):
            return

        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}

            for key, config_data in data.items():
                self._custom_profiles[key] = ProfileConfig(
                    name=config_data.get("name", key),
                    description=config_data.get("description", ""),
                    tools=config_data.get("tools", []),
                    models=config_data.get("models", []),
                    install_configs=config_data.get("install_configs", {}),
                    requires_docker=config_data.get("requires_docker", False),
                    requires_gpu=config_data.get("requires_gpu", False),
                    estimated_disk_gb=config_data.get("estimated_disk_gb", 10),
                )

            logger.info("Custom profiles loaded", count=len(self._custom_profiles))
        except Exception as e:
            logger.error("Failed to load custom profiles", error=str(e))

    def _get_default_profiles_dir(self) -> str:
        """Get default profiles directory."""
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config", "deployment",
        )
