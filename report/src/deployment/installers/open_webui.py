"""
Corax Orchestrator - Open WebUI Installer.

Deploys Open WebUI as a Docker container or local Python service.
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


class OpenWebUIInstaller(AIInstallerBase):
    """
    Open WebUI installer - Web UI for local LLMs.

    Supports:
    - Docker deployment (recommended)
    - Local Python deployment (pip)
    - Ollama backend integration
    """

    OPEN_WEBUI_DEFAULT_PORT = 3000
    DOCKER_IMAGE = "ghcr.io/open-webui/open-webui:main"

    @property
    def tool_name(self) -> str:
        return "Open WebUI"

    @property
    def tool_key(self) -> str:
        return "open_webui"

    @property
    def description(self) -> str:
        return "Web UI for interacting with local LLMs via Ollama"

    @property
    def default_port(self) -> Optional[int]:
        return self.OPEN_WEBUI_DEFAULT_PORT

    @property
    def min_disk_gb(self) -> int:
        return 1

    @property
    def dependencies(self) -> List[str]:
        return ["ollama"]

    async def detect(self) -> InstallResult:
        """Detect if Open WebUI is installed."""
        # Check Docker container
        docker_path = self._find_in_path("docker")
        if docker_path:
            code, stdout, _ = await self._run_command(
                ["docker", "ps", "--filter", "name=open-webui",
                 "--format", "{{.Names}}"],
                timeout=15,
            )
            if "open-webui" in stdout:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    port=self.OPEN_WEBUI_DEFAULT_PORT,
                    details={"detected_via": "docker", "container": "open-webui"},
                )

        # Check pip installation
        code, stdout, _ = await self._run_command(
            ["pip", "show", "open-webui"],
            timeout=15,
        )
        if code == 0:
            version = "unknown"
            for line in stdout.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.INSTALLED,
                version=version,
                details={"detected_via": "pip"},
            )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install Open WebUI."""
        config = config or {}
        logger.info("Installing Open WebUI")

        try:
            # Prefer Docker if available
            docker_path = self._find_in_path("docker")
            if docker_path:
                return await self._install_docker(config)
            else:
                return await self._install_pip(config)
        except Exception as e:
            logger.error("Open WebUI installation failed", error=str(e))
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def _install_docker(self, config: Dict[str, Any]) -> InstallResult:
        """Install Open WebUI via Docker."""
        ollama_url = config.get("ollama_url", "http://host.docker.internal:11434")
        data_dir = config.get("data_dir", self._get_open_webui_data_dir())

        os.makedirs(data_dir, exist_ok=True)

        code, stdout, stderr = await self._run_command([
            "docker", "run", "-d",
            "--name", "open-webui",
            "-p", f"{self.OPEN_WEBUI_DEFAULT_PORT}:8080",
            "-v", f"{data_dir}:/app/backend/data",
            "-e", f"OLLAMA_BASE_URL={ollama_url}",
            "--restart", "unless-stopped",
            self.DOCKER_IMAGE,
        ], timeout=120)

        if code != 0:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=f"Docker run failed: {stderr[:500]}",
            )

        # Wait for container to start
        await asyncio.sleep(5)
        return await self.verify()

    async def _install_pip(self, config: Dict[str, Any]) -> InstallResult:
        """Install Open WebUI via pip."""
        code, stdout, stderr = await self._run_command(
            ["pip", "install", "open-webui"],
            timeout=300,
        )

        if code != 0:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=f"pip install failed: {stderr[:500]}",
            )

        return await self.verify()

    async def verify(self) -> InstallResult:
        """Verify Open WebUI installation."""
        # Check Docker container
        docker_path = self._find_in_path("docker")
        if docker_path:
            code, stdout, _ = await self._run_command(
                ["docker", "ps", "--filter", "name=open-webui",
                 "--format", "{{.Status}}"],
                timeout=15,
            )
            if "Up" in stdout:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    port=self.OPEN_WEBUI_DEFAULT_PORT,
                    details={
                        "deployment": "docker",
                        "container_status": stdout.strip(),
                    },
                )

        # Check pip
        code, stdout, _ = await self._run_command(
            ["pip", "show", "open-webui"],
            timeout=15,
        )
        if code == 0:
            version = "unknown"
            for line in stdout.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.INSTALLED,
                version=version,
                details={"deployment": "pip"},
            )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.FAILED,
            error="Open WebUI not found",
        )

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """Configure Open WebUI."""
        updates = []

        if "ollama_url" in config:
            # Update Docker container env
            docker_path = self._find_in_path("docker")
            if docker_path:
                await self._run_command([
                    "docker", "stop", "open-webui",
                ], timeout=30)
                await self._run_command([
                    "docker", "rm", "open-webui",
                ], timeout=30)
                # Recreate with new config
                result = await self._install_docker(config)
                if result.status == InstallStatus.INSTALLED:
                    updates.append("ollama_url")

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            details={"configured": updates},
        )

    async def uninstall(self) -> InstallResult:
        """Uninstall Open WebUI."""
        docker_path = self._find_in_path("docker")
        if docker_path:
            await self._run_command(["docker", "stop", "open-webui"], timeout=30)
            await self._run_command(["docker", "rm", "open-webui"], timeout=30)
            await self._run_command(
                ["docker", "image", "rm", self.DOCKER_IMAGE],
                timeout=60,
            )

        await self._run_command(["pip", "uninstall", "-y", "open-webui"], timeout=60)

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    def _get_open_webui_data_dir(self) -> str:
        """Get Open WebUI data directory."""
        if self._is_windows:
            return self._get_roaming_appdata_path("Open WebUI", "data")
        elif self._is_macos:
            return os.path.expanduser("~/.open-webui/data")
        else:
            return os.path.expanduser("~/.open-webui/data")
