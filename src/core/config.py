"""
Corax Orchestrator - Configuration Management.

Provides hierarchical configuration management with:
- YAML and JSON config file support
- Environment variable overrides
- CLI argument overrides
- Config validation
- Schema enforcement
- Hot-reload support
"""

import os
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from copy import deepcopy

import yaml

from src.core.exceptions import ConfigurationError
from src.core.logging import get_logger

logger = get_logger(__name__)


def _is_frozen() -> bool:
    """Detect if running as a PyInstaller executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _get_bundle_root() -> Optional[str]:
    """Get the PyInstaller bundle root if frozen."""
    if _is_frozen():
        return getattr(sys, "_MEIPASS", None)
    return None


def _resolve_config_dir(config_dir: Optional[Path]) -> Path:
    """Resolve config directory with frozen-executable fallback."""
    if config_dir is not None:
        return config_dir
    if _is_frozen():
        bundle = _get_bundle_root()
        if bundle:
            return Path(os.path.join(os.path.dirname(bundle), "config"))
        # Frozen without bundle: fallback to home dir
        return Path(os.path.expanduser("~")) / ".corax" / "config"
    return Path("config")

# Type for nested configuration dictionaries
ConfigDict = Dict[str, Any]


class ConfigSchema:
    """
    Defines the configuration schema for validation.

    Each key can have:
    - type: expected Python type
    - required: whether the key is mandatory
    - default: default value if not provided
    - description: human-readable description
    - nested: nested schema for dict values
    """

    def __init__(self, schema: Dict[str, Any]) -> None:
        self.schema = schema

    def validate(self, config: ConfigDict, path: str = "") -> List[str]:
        """Validate a configuration against the schema."""
        errors: List[str] = []

        for key, rules in self.schema.items():
            full_path = f"{path}.{key}" if path else key

            if key not in config:
                if rules.get("required", False):
                    errors.append(f"Missing required config: {full_path}")
                continue

            value = config[key]
            expected_type = rules.get("type")

            if expected_type and not isinstance(value, expected_type):
                errors.append(
                    f"Config '{full_path}' expected type "
                    f"{expected_type.__name__}, got {type(value).__name__}"
                )

            if isinstance(value, dict) and "nested" in rules:
                nested_errors = ConfigSchema(rules["nested"]).validate(
                    value, full_path
                )
                errors.extend(nested_errors)

        return errors


# Default configuration schema
DEFAULT_SCHEMA = ConfigSchema(
    {
        "project": {
            "type": dict,
            "required": True,
            "description": "Project metadata",
            "nested": {
                "name": {"type": str, "required": True},
                "version": {"type": str, "required": True},
                "description": {"type": str, "default": ""},
            },
        },
        "logging": {
            "type": dict,
            "required": False,
            "description": "Logging configuration",
            "nested": {
                "level": {"type": str, "default": "INFO"},
                "directory": {"type": str, "default": "data/logs"},
                "json_output": {"type": bool, "default": False},
                "max_bytes": {"type": int, "default": 10485760},
                "backup_count": {"type": int, "default": 5},
            },
        },
        "platform": {
            "type": dict,
            "required": False,
            "description": "Platform-specific settings",
            "nested": {
                "preferred_shell": {"type": str, "default": "auto"},
                "use_powershell": {"type": bool, "default": True},
                "admin_required": {"type": bool, "default": False},
            },
        },
        "tools": {
            "type": dict,
            "required": False,
            "description": "Tool installation settings",
            "nested": {
                "install_dir": {"type": str, "default": "%USERPROFILE%\\CoraxTools"},
                "auto_accept": {"type": bool, "default": False},
                "verify_checksums": {"type": bool, "default": True},
                "timeout_seconds": {"type": int, "default": 300},
                "retry_attempts": {"type": int, "default": 3},
            },
        },
        "models": {
            "type": dict,
            "required": False,
            "description": "AI model management settings",
            "nested": {
                "download_dir": {"type": str, "default": "data/models"},
                "max_concurrent_downloads": {"type": int, "default": 2},
                "default_quantization": {"type": str, "default": "Q4_K_M"},
                "hf_mirror": {"type": str, "default": ""},
            },
        },
        "persistence": {
            "type": dict,
            "required": False,
            "description": "State persistence settings",
            "nested": {
                "directory": {"type": str, "default": "data/persistence"},
                "format": {"type": str, "default": "json"},
                "auto_save_interval": {"type": int, "default": 30},
            },
        },
        "self_healing": {
            "type": dict,
            "required": False,
            "description": "Self-healing engine settings",
            "nested": {
                "enabled": {"type": bool, "default": True},
                "max_retries": {"type": int, "default": 3},
                "retry_delay_seconds": {"type": int, "default": 5},
                "health_check_interval": {"type": int, "default": 60},
            },
        },
        "reporting": {
            "type": dict,
            "required": False,
            "description": "Reporting engine settings",
            "nested": {
                "output_dir": {"type": str, "default": "data/reports"},
                "formats": {
                    "type": list,
                    "default": ["json", "html", "markdown"],
                },
                "include_system_info": {"type": bool, "default": True},
            },
        },
    }
)


class ConfigManager:
    """
    Hierarchical configuration manager.

    Loads configuration from multiple sources with the following priority
    (highest to lowest):
    1. CLI arguments
    2. Environment variables
    3. User config file (~/.corax/config.yaml)
    4. Project config file (config/corax.yaml)
    5. Default values
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        schema: Optional[ConfigSchema] = None,
    ) -> None:
        self.config_dir = _resolve_config_dir(config_dir)
        self.schema = schema or DEFAULT_SCHEMA
        self._config: ConfigDict = {}
        self._loaded_files: List[Path] = []
        self._env_prefix = "CORAX_"

    def load(self) -> ConfigDict:
        """Load configuration from all sources."""
        config: ConfigDict = {}

        # 1. Start with defaults from schema
        config = self._apply_defaults(self.schema.schema)

        # 2. Load project config file
        project_config = self.config_dir / "corax.yaml"
        if project_config.exists():
            loaded = self._load_file(project_config)
            config = self._deep_merge(config, loaded)
            self._loaded_files.append(project_config)
            logger.info("Loaded project config", path=str(project_config))

        # 3. Load user config file
        user_config = Path.home() / ".corax" / "config.yaml"
        if user_config.exists():
            loaded = self._load_file(user_config)
            config = self._deep_merge(config, loaded)
            self._loaded_files.append(user_config)
            logger.info("Loaded user config", path=str(user_config))

        # 4. Apply environment variable overrides
        config = self._apply_env_overrides(config)

        # 5. Validate
        errors = self.schema.validate(config)
        if errors:
            for error in errors:
                logger.warning("Config validation warning", error=error)

        self._config = config
        logger.info(
            "Configuration loaded",
            sources=[str(p) for p in self._loaded_files],
        )
        return config

    def reload(self) -> ConfigDict:
        """Reload configuration from disk."""
        logger.info("Reloading configuration")
        return self.load()

    def get(
        self, key: str, default: Any = None
    ) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Dot-separated key path (e.g., 'logging.level')
            default: Default value if key not found

        Returns:
            The configuration value or default
        """
        parts = key.split(".")
        value = self._config
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.

        Args:
            key: Dot-separated key path (e.g., 'logging.level')
            value: Value to set
        """
        parts = key.split(".")
        target = self._config
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    def to_dict(self) -> ConfigDict:
        """Export full configuration as dictionary."""
        return deepcopy(self._config)

    def save(self, path: Optional[Path] = None) -> None:
        """Save current configuration to a file."""
        save_path = path or (self.config_dir / "corax.yaml")
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)

        logger.info("Configuration saved", path=str(save_path))

    def _load_file(self, path: Path) -> ConfigDict:
        """Load a configuration file (YAML or JSON)."""
        suffix = path.suffix.lower()
        try:
            with open(path, "r") as f:
                if suffix in (".yaml", ".yml"):
                    return yaml.safe_load(f) or {}
                elif suffix == ".json":
                    return json.load(f)
                else:
                    logger.warning(
                        "Unsupported config format", path=str(path), suffix=suffix
                    )
                    return {}
        except Exception as e:
            raise ConfigurationError(
                message=f"Failed to load config file: {path}",
                config_key=str(path),
                details={"error": str(e)},
            )

    def _apply_defaults(self, schema: Dict[str, Any], prefix: str = "") -> ConfigDict:
        """Apply default values from schema."""
        config: ConfigDict = {}
        for key, rules in schema.items():
            if "default" in rules:
                config[key] = deepcopy(rules["default"])
            elif "nested" in rules:
                config[key] = self._apply_defaults(rules["nested"], f"{prefix}.{key}")
            elif rules.get("type") == dict:
                config[key] = {}
        return config

    def _apply_env_overrides(self, config: ConfigDict) -> ConfigDict:
        """Apply environment variable overrides."""
        for env_key, env_value in os.environ.items():
            if env_key.startswith(self._env_prefix):
                # CORAX_LOGGING_LEVEL -> logging.level
                config_path = (
                    env_key[len(self._env_prefix) :]
                    .lower()
                    .replace("__", ".")
                    .replace("_", ".")
                )
                # Try to parse as JSON for complex types
                try:
                    parsed = json.loads(env_value)
                except (json.JSONDecodeError, TypeError):
                    parsed = env_value

                self._set_nested(config, config_path.split("."), parsed)

        return config

    def _set_nested(
        self, config: ConfigDict, keys: List[str], value: Any
    ) -> None:
        """Set a value in a nested dictionary."""
        target = config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def _deep_merge(self, base: ConfigDict, override: ConfigDict) -> ConfigDict:
        """Deep merge two configuration dictionaries."""
        result = deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    @property
    def loaded_files(self) -> List[Path]:
        """Get list of loaded configuration files."""
        return list(self._loaded_files)


def load_config(config_path: Optional[Path] = None) -> ConfigDict:
    """
    Convenience function to load configuration.

    Args:
        config_path: Optional path to a specific config file.
                     If None, uses the default config directory.

    Returns:
        Configuration dictionary
    """
    if config_path:
        config_dir = config_path.parent if config_path.is_file() else config_path
    else:
        config_dir = _resolve_config_dir(None)

    manager = ConfigManager(config_dir=config_dir)
    return manager.load()
