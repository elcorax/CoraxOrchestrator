"""
Corax Orchestrator - LM Studio Installer.

Real deployment support for LM Studio local LLM runtime.
Handles detection, installation, verification, and configuration.
"""

from typing import Dict, Any, List, Optional
import asyncio
import json
import os
import shutil
import tempfile

from src.deployment.installers.base import (
    AIInstallerBase,
    InstallResult,
    InstallStatus,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class LMStudioInstaller(AIInstallerBase):
    """
    LM Studio installer - GUI-based local LLM runtime.

    Features:
    - Windows: Download and install .exe
    - macOS: Download and install .dmg
    - API endpoint verification (OpenAI-compatible)
    - Model directory configuration
    """

    LM_STUDIO_DOWNLOAD_URLS = {
        "windows": "https://installers.lmstudio.ai/windows/LM-Studio-Setup.exe",
        "darwin": "https://installers.lmstudio.ai/mac/LM-Studio.dmg",
    }

    LM_STUDIO_DEFAULT_PORT = 1234
    LM_STUDIO_API_URL = "http://localhost:1234/v1"

    @property
    def tool_name(self) -> str:
        return "LM Studio"

    @property
    def tool_key(self) -> str:
        return "lm_studio"

    @property
    def description(self) -> str:
        return "GUI-based local LLM runtime with OpenAI-compatible API"

    @property
    def default_port(self) -> Optional[int]:
        return self.LM_STUDIO_DEFAULT_PORT

    @property
    def min_disk_gb(self) -> int:
        return 1

    @property
    def dependencies(self) -> List[str]:
        return []

    async def detect(self) -> InstallResult:
        """Detect if LM Studio is installed."""
        # Check common install paths
        install_paths = self._get_common_paths()
        for path in install_paths:
            if os.path.exists(path):
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    install_path=path,
                    port=self.LM_STUDIO_DEFAULT_PORT,
                    details={"detected_via": "common_path"},
                )

        # Check if running via process
        if self._is_windows:
            code, stdout, _ = await self._run_powershell(
                "Get-Process 'LM Studio' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path"
            )
            if stdout.strip():
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    install_path=stdout.strip(),
                    port=self.LM_STUDIO_DEFAULT_PORT,
                    details={"detected_via": "process"},
                )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install LM Studio."""
        config = config or {}
        logger.info("Installing LM Studio")

        try:
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
            logger.error("LM Studio installation failed", error=str(e))
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def _install_windows(self, config: Dict[str, Any]) -> InstallResult:
        """Install LM Studio on Windows."""
        temp_dir = tempfile.mkdtemp()
        installer_path = os.path.join(temp_dir, "LM-Studio-Setup.exe")

        try:
            logger.info("Downloading LM Studio installer")
            success = await self._download_file(
                self.LM_STUDIO_DOWNLOAD_URLS["windows"],
                installer_path,
                timeout=600,
            )
            if not success:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error="Failed to download LM Studio installer",
                )

            logger.info("Running LM Studio installer")
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
        """Install LM Studio on macOS."""
        temp_dir = tempfile.mkdtemp()
        dmg_path = os.path.join(temp_dir, "LM-Studio.dmg")

        try:
            logger.info("Downloading LM Studio for macOS")
            success = await self._download_file(
                self.LM_STUDIO_DOWNLOAD_URLS["darwin"],
                dmg_path,
                timeout=600,
            )
            if not success:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error="Failed to download LM Studio",
                )

            # Mount DMG and copy app
            mount_point = os.path.join(temp_dir, "mnt")
            os.makedirs(mount_point, exist_ok=True)

            await self._run_command([
                "hdiutil", "attach", dmg_path, "-mountpoint", mount_point
            ], timeout=60)

            await asyncio.sleep(2)

            await self._run_command([
                "cp", "-R", os.path.join(mount_point, "LM Studio.app"),
                "/Applications/"
            ], timeout=120)

            await self._run_command([
                "hdiutil", "detach", mount_point
            ], timeout=30)

            return await self.verify()

        finally:
            try:
                if os.path.exists(dmg_path):
                    os.remove(dmg_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def verify(self) -> InstallResult:
        """Verify LM Studio installation."""
        install_paths = self._get_common_paths()
        found_path = None
        for path in install_paths:
            if os.path.exists(path):
                found_path = path
                break

        if not found_path:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error="LM Studio not found after installation",
            )

        # Test API endpoint
        api_available = await self._test_api()

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            install_path=found_path,
            port=self.LM_STUDIO_DEFAULT_PORT,
            details={
                "api_available": api_available,
                "binary_path": found_path,
            },
        )

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """Configure LM Studio settings."""
        config_path = self._get_config_path()
        updates = []

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                settings = {}

            if "models_dir" in config:
                settings["modelsDir"] = config["models_dir"]
                updates.append("models_dir")

            if "port" in config:
                settings["port"] = config["port"]
                updates.append("port")

            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(settings, f, indent=2)

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            config_path=config_path,
            details={"configured": updates},
        )

    async def _test_api(self) -> bool:
        """Test LM Studio API endpoint."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.LM_STUDIO_API_URL}/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def _get_config_path(self) -> Optional[str]:
        """Get LM Studio config file path."""
        if self._is_windows:
            return self._get_roaming_appdata_path(
                "LM Studio", "settings.json"
            )
        elif self._is_macos:
            return os.path.expanduser(
                "~/Library/Application Support/LM Studio/settings.json"
            )
        return None

    def _get_common_paths(self) -> List[str]:
        """Get common LM Studio install paths."""
        paths = []
        if self._is_windows:
            paths.extend([
                self._get_local_appdata_path("Programs", "LM Studio", "LM Studio.exe"),
                os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\LM Studio\LM Studio.exe"),
            ])
        elif self._is_macos:
            paths.extend([
                "/Applications/LM Studio.app",
                os.path.expanduser("~/Applications/LM Studio.app"),
            ])
        return paths
