"""
Corax Orchestrator - AnythingLLM Installer.

Deploys AnythingLLM for local document RAG capabilities.
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


class AnythingLLMInstaller(AIInstallerBase):
    """
    AnythingLLM installer - Local document RAG system.

    Supports:
    - Windows: Download and install .exe
    - macOS: Download and install .dmg
    - Docker deployment
    - Local LLM backend configuration
    """

    ANYTHINGLLM_DOWNLOAD_URLS = {
        "windows": "https://anythingllm.com/download/windows",
        "darwin": "https://anythingllm.com/download/macos",
    }

    ANYTHINGLLM_DEFAULT_PORT = 3001
    DOCKER_IMAGE = "mintplexlabs/anythingllm:latest"

    @property
    def tool_name(self) -> str:
        return "AnythingLLM"

    @property
    def tool_key(self) -> str:
        return "anythingllm"

    @property
    def description(self) -> str:
        return "Local document RAG system for AI-powered document interaction"

    @property
    def default_port(self) -> Optional[int]:
        return self.ANYTHINGLLM_DEFAULT_PORT

    @property
    def min_disk_gb(self) -> int:
        return 2

    @property
    def dependencies(self) -> List[str]:
        return []

    async def detect(self) -> InstallResult:
        """Detect if AnythingLLM is installed."""
        # Check common install paths
        install_paths = self._get_common_paths()
        for path in install_paths:
            if os.path.exists(path):
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    install_path=path,
                    port=self.ANYTHINGLLM_DEFAULT_PORT,
                    details={"detected_via": "common_path"},
                )

        # Check Docker
        docker_path = self._find_in_path("docker")
        if docker_path:
            code, stdout, _ = await self._run_command(
                ["docker", "ps", "--filter", "name=anythingllm",
                 "--format", "{{.Names}}"],
                timeout=15,
            )
            if "anythingllm" in stdout:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    port=self.ANYTHINGLLM_DEFAULT_PORT,
                    details={"detected_via": "docker"},
                )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install AnythingLLM."""
        config = config or {}
        logger.info("Installing AnythingLLM")

        try:
            docker_path = self._find_in_path("docker")
            if docker_path:
                return await self._install_docker(config)

            if self._is_windows:
                return await self._install_windows(config)
            elif self._is_macos:
                return await self._install_macos(config)
            else:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=f"Unsupported platform: {self._system}",
                )
        except Exception as e:
            logger.error("AnythingLLM installation failed", error=str(e))
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def _install_docker(self, config: Dict[str, Any]) -> InstallResult:
        """Install AnythingLLM via Docker."""
        data_dir = config.get("data_dir", self._get_data_dir())
        os.makedirs(data_dir, exist_ok=True)

        code, stdout, stderr = await self._run_command([
            "docker", "run", "-d",
            "--name", "anythingllm",
            "-p", f"{self.ANYTHINGLLM_DEFAULT_PORT}:3001",
            "-v", f"{data_dir}:/app/server/storage",
            "-e", "STORAGE_DIR=/app/server/storage",
            "--restart", "unless-stopped",
            self.DOCKER_IMAGE,
        ], timeout=120)

        if code != 0:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=f"Docker run failed: {stderr[:500]}",
            )

        await asyncio.sleep(5)
        return await self.verify()

    async def _install_windows(self, config: Dict[str, Any]) -> InstallResult:
        """Install AnythingLLM on Windows."""
        temp_dir = tempfile.mkdtemp()
        installer_path = os.path.join(temp_dir, "AnythingLLM-Setup.exe")

        try:
            logger.info("Downloading AnythingLLM installer")
            success = await self._download_file(
                self.ANYTHINGLLM_DOWNLOAD_URLS["windows"],
                installer_path,
                timeout=600,
            )
            if not success:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error="Failed to download AnythingLLM installer",
                )

            code, stdout, stderr = await self._run_command(
                [installer_path, "/S"],
                timeout=300,
            )

            if code != 0:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=f"Installer failed: {stderr[:500]}",
                )

            await asyncio.sleep(5)
            return await self.verify()

        finally:
            try:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def _install_macos(self, config: Dict[str, Any]) -> InstallResult:
        """Install AnythingLLM on macOS."""
        temp_dir = tempfile.mkdtemp()
        dmg_path = os.path.join(temp_dir, "AnythingLLM.dmg")

        try:
            logger.info("Downloading AnythingLLM for macOS")
            success = await self._download_file(
                self.ANYTHINGLLM_DOWNLOAD_URLS["darwin"],
                dmg_path,
                timeout=600,
            )
            if not success:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error="Failed to download AnythingLLM",
                )

            mount_point = os.path.join(temp_dir, "mnt")
            os.makedirs(mount_point, exist_ok=True)

            await self._run_command([
                "hdiutil", "attach", dmg_path, "-mountpoint", mount_point
            ], timeout=60)
            await asyncio.sleep(2)

            await self._run_command([
                "cp", "-R", os.path.join(mount_point, "AnythingLLM.app"),
                "/Applications/"
            ], timeout=120)

            await self._run_command(["hdiutil", "detach", mount_point], timeout=30)

            return await self.verify()

        finally:
            try:
                if os.path.exists(dmg_path):
                    os.remove(dmg_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def verify(self) -> InstallResult:
        """Verify AnythingLLM installation."""
        # Check Docker
        docker_path = self._find_in_path("docker")
        if docker_path:
            code, stdout, _ = await self._run_command(
                ["docker", "ps", "--filter", "name=anythingllm",
                 "--format", "{{.Status}}"],
                timeout=15,
            )
            if "Up" in stdout:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    port=self.ANYTHINGLLM_DEFAULT_PORT,
                    details={"deployment": "docker"},
                )

        # Check native install
        install_paths = self._get_common_paths()
        for path in install_paths:
            if os.path.exists(path):
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    install_path=path,
                    port=self.ANYTHINGLLM_DEFAULT_PORT,
                    details={"deployment": "native"},
                )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.FAILED,
            error="AnythingLLM not found",
        )

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """Configure AnythingLLM."""
        config_path = self._get_config_path()
        updates = []

        if config_path:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            existing = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        existing = json.load(f)
                except json.JSONDecodeError:
                    pass

            if "llm_provider" in config:
                existing["LLM_PROVIDER"] = config["llm_provider"]
                updates.append("llm_provider")
            if "ollama_endpoint" in config:
                existing["OLLAMA_ENDPOINT"] = config["ollama_endpoint"]
                updates.append("ollama_endpoint")

            with open(config_path, "w") as f:
                json.dump(existing, f, indent=2)

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            config_path=config_path,
            details={"configured": updates},
        )

    def _get_common_paths(self) -> List[str]:
        """Get common AnythingLLM install paths."""
        paths = []
        if self._is_windows:
            paths.extend([
                self._get_local_appdata_path("Programs", "AnythingLLM", "AnythingLLM.exe"),
                os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\AnythingLLM\AnythingLLM.exe"),
            ])
        elif self._is_macos:
            paths.extend([
                "/Applications/AnythingLLM.app",
                os.path.expanduser("~/Applications/AnythingLLM.app"),
            ])
        return paths

    def _get_data_dir(self) -> str:
        """Get AnythingLLM data directory."""
        if self._is_windows:
            return self._get_roaming_appdata_path("AnythingLLM")
        elif self._is_macos:
            return os.path.expanduser("~/Library/Application Support/AnythingLLM")
        else:
            return os.path.expanduser("~/.anythingllm")

    def _get_config_path(self) -> Optional[str]:
        """Get AnythingLLM config file path."""
        return os.path.join(self._get_data_dir(), ".env")
