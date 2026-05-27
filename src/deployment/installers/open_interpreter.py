"""
Corax Orchestrator - Open Interpreter Installer.

Deploys Open Interpreter for local AI agent capabilities.
"""

from typing import Dict, Any, List, Optional
import asyncio
import json
import os
import tempfile

from src.deployment.installers.base import (
    AIInstallerBase,
    InstallResult,
    InstallStatus,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class OpenInterpreterInstaller(AIInstallerBase):
    """
    Open Interpreter installer - Local AI agent runtime.

    Supports:
    - pip installation
    - Virtual environment setup
    - LLM backend configuration (Ollama, LM Studio)
    - Profile management
    """

    @property
    def tool_name(self) -> str:
        return "Open Interpreter"

    @property
    def tool_key(self) -> str:
        return "open_interpreter"

    @property
    def description(self) -> str:
        return "Local AI agent runtime for natural language code execution"

    @property
    def default_port(self) -> Optional[int]:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 1

    @property
    def dependencies(self) -> List[str]:
        return ["python"]

    async def detect(self) -> InstallResult:
        """Detect if Open Interpreter is installed."""
        # Check pip
        code, stdout, _ = await self._run_command(
            ["pip", "show", "open-interpreter"],
            timeout=15,
        )
        if code == 0:
            version = "unknown"
            for line in stdout.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                if line.startswith("Location:"):
                    location = line.split(":", 1)[1].strip()

            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.INSTALLED,
                version=version,
                install_path=location if 'location' in dir() else None,
                details={"detected_via": "pip"},
            )

        # Check if interpreter binary exists
        interpreter_path = self._find_in_path("interpreter")
        if interpreter_path:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.INSTALLED,
                install_path=interpreter_path,
                details={"detected_via": "path"},
            )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install Open Interpreter."""
        config = config or {}
        logger.info("Installing Open Interpreter")

        try:
            # Create virtual environment if requested
            venv_path = config.get("venv_path")
            if venv_path:
                os.makedirs(os.path.dirname(venv_path), exist_ok=True)
                code, stdout, stderr = await self._run_command(
                    ["python", "-m", "venv", venv_path],
                    timeout=120,
                )
                if code != 0:
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.FAILED,
                        error=f"Virtual env creation failed: {stderr[:500]}",
                    )

                pip_path = os.path.join(
                    venv_path, "Scripts", "pip"
                ) if self._is_windows else os.path.join(
                    venv_path, "bin", "pip"
                )

                code, stdout, stderr = await self._run_command(
                    [pip_path, "install", "open-interpreter"],
                    timeout=300,
                )
            else:
                # Install globally
                code, stdout, stderr = await self._run_command(
                    ["pip", "install", "open-interpreter"],
                    timeout=300,
                )

            if code != 0:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=f"pip install failed: {stderr[:500]}",
                )

            return await self.verify()

        except Exception as e:
            logger.error("Open Interpreter installation failed", error=str(e))
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def verify(self) -> InstallResult:
        """Verify Open Interpreter installation."""
        # Check pip
        code, stdout, _ = await self._run_command(
            ["pip", "show", "open-interpreter"],
            timeout=15,
        )
        if code == 0:
            version = "unknown"
            location = None
            for line in stdout.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                if line.startswith("Location:"):
                    location = line.split(":", 1)[1].strip()

            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.INSTALLED,
                version=version,
                install_path=location,
                details={"detected_via": "pip"},
            )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.FAILED,
            error="Open Interpreter not found",
        )

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """Configure Open Interpreter."""
        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)

        config_file = os.path.join(config_dir, "config.yaml")
        updates = []

        # Write configuration
        import yaml
        profile = {
            "llm": {
                "model": config.get("model", "ollama/llama3.2"),
                "api_base": config.get("api_base", "http://localhost:11434"),
                "api_key": config.get("api_key", ""),
            },
            "custom_instructions": config.get("custom_instructions", ""),
            "auto_run": config.get("auto_run", False),
            "verbose": config.get("verbose", True),
        }

        with open(config_file, "w") as f:
            yaml.dump(profile, f, default_flow_style=False)

        updates.extend(["model", "api_base"])

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            config_path=config_file,
            details={"configured": updates},
        )

    async def uninstall(self) -> InstallResult:
        """Uninstall Open Interpreter."""
        await self._run_command(
            ["pip", "uninstall", "-y", "open-interpreter"],
            timeout=60,
        )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    def _get_config_dir(self) -> str:
        """Get Open Interpreter config directory."""
        if self._is_windows:
            return self._get_roaming_appdata_path("Open Interpreter")
        elif self._is_macos:
            return os.path.expanduser("~/.config/open-interpreter")
        else:
            return os.path.expanduser("~/.config/open-interpreter")
