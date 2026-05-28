"""
Corax Orchestrator - Ollama Installer.

Real deployment support for Ollama local LLM runtime.
Handles detection, installation, verification, configuration,
and service management across Windows and macOS.
"""

from typing import Dict, Any, List, Optional
import asyncio
import json
import os
import platform
import shutil
import tempfile

from src.deployment.installers.base import (
    AIInstallerBase,
    InstallResult,
    InstallStatus,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class OllamaInstaller(AIInstallerBase):
    """
    Ollama local LLM runtime installer.

    Features:
    - Windows: Download and run official installer
    - macOS: Download and install .app bundle
    - Linux: curl-based installation script
    - Service management (start/stop/restart)
    - API endpoint verification
    - Model management integration
    """

    OLLAMA_DOWNLOAD_URLS = {
        "windows": "https://ollama.com/download/OllamaSetup.exe",
        "darwin": "https://ollama.com/download/Ollama-darwin.zip",
        "linux": "https://ollama.com/install.sh",
    }

    OLLAMA_DEFAULT_PORT = 11434
    OLLAMA_API_URL = "http://localhost:11434"

    @property
    def tool_name(self) -> str:
        return "Ollama"

    @property
    def tool_key(self) -> str:
        return "ollama"

    @property
    def description(self) -> str:
        return "Local LLM runtime for running open-source language models"

    @property
    def default_port(self) -> Optional[int]:
        return self.OLLAMA_DEFAULT_PORT

    @property
    def min_disk_gb(self) -> int:
        return 2

    @property
    def dependencies(self) -> List[str]:
        return []

    async def detect(self) -> InstallResult:
        """Detect if Ollama is installed."""
        # Check for ollama in PATH
        ollama_path = self._find_in_path("ollama")
        if ollama_path:
            # Get version
            code, stdout, stderr = await self._run_command(["ollama", "--version"])
            if code == 0:
                version = stdout.strip() or stderr.strip()
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    version=version,
                    install_path=ollama_path,
                    port=self.OLLAMA_DEFAULT_PORT,
                    details={"detected_via": "path"},
                )

        # Check common install locations
        install_paths = self._get_common_paths()
        for path in install_paths:
            if os.path.exists(path):
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    install_path=path,
                    port=self.OLLAMA_DEFAULT_PORT,
                    details={"detected_via": "common_path", "path": path},
                )

        # Check if service is running
        if self._is_windows:
            code, stdout, _ = await self._run_powershell(
                "Get-Service ollama -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Status"
            )
            if "Running" in stdout:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    port=self.OLLAMA_DEFAULT_PORT,
                    details={"detected_via": "service"},
                )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install Ollama."""
        config = config or {}
        logger.info("Installing Ollama")

        try:
            if self._is_windows:
                return await self._install_windows(config)
            elif self._is_macos:
                return await self._install_macos(config)
            elif self._is_linux:
                return await self._install_linux(config)
            else:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=f"Unsupported platform: {self._system}",
                )
        except Exception as e:
            logger.error("Ollama installation failed", error=str(e))
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def _install_windows(self, config: Dict[str, Any]) -> InstallResult:
        """Install Ollama on Windows."""
        temp_dir = tempfile.mkdtemp()
        installer_path = os.path.join(temp_dir, "OllamaSetup.exe")

        try:
            # Download installer
            logger.info("Downloading Ollama installer")
            success = await self._download_file(
                self.OLLAMA_DOWNLOAD_URLS["windows"],
                installer_path,
                timeout=600,
            )
            if not success:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error="Failed to download Ollama installer",
                )

            # Run installer silently
            logger.info("Running Ollama installer")
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

            # Wait for installation to complete
            await asyncio.sleep(5)

            # Verify installation
            return await self.verify()

        finally:
            # Cleanup
            try:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def _install_macos(self, config: Dict[str, Any]) -> InstallResult:
        """Install Ollama on macOS."""
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, "Ollama.zip")

        try:
            # Download
            logger.info("Downloading Ollama for macOS")
            success = await self._download_file(
                self.OLLAMA_DOWNLOAD_URLS["darwin"],
                zip_path,
                timeout=600,
            )
            if not success:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error="Failed to download Ollama",
                )

            # Extract and install
            code, stdout, stderr = await self._run_command([
                "unzip", "-o", zip_path, "-d", "/Applications/"
            ], timeout=120)

            if code != 0:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=f"Extraction failed: {stderr[:500]}",
                )

            return await self.verify()

        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def _install_linux(self, config: Dict[str, Any]) -> InstallResult:
        """Install Ollama on Linux."""
        code, stdout, stderr = await self._run_command(
            ["curl", "-fsSL", self.OLLAMA_DOWNLOAD_URLS["linux"]],
            timeout=60,
        )

        if code != 0:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=f"Failed to download install script: {stderr[:500]}",
            )

        # Pipe to sh
        proc = await asyncio.create_subprocess_shell(
            f"curl -fsSL {self.OLLAMA_DOWNLOAD_URLS['linux']} | sh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=f"Installation failed: {stderr[:500]}",
            )

        return await self.verify()

    async def verify(self) -> InstallResult:
        """Verify Ollama installation."""
        # Check if ollama binary exists
        ollama_path = self._find_in_path("ollama")
        if not ollama_path:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error="Ollama binary not found after installation",
            )

        # Get version
        code, stdout, stderr = await self._run_command(["ollama", "--version"])
        version = stdout.strip() or stderr.strip() if code == 0 else "unknown"

        # Check if service is running
        service_running = await self._check_service_running()

        # Test API endpoint
        api_available = await self._test_api()

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            version=version,
            install_path=ollama_path,
            port=self.OLLAMA_DEFAULT_PORT,
            details={
                "service_running": service_running,
                "api_available": api_available,
                "binary_path": ollama_path,
            },
        )

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """Configure Ollama settings."""
        updates = []

        # Set environment variables
        if "models_dir" in config:
            os.environ["OLLAMA_MODELS"] = config["models_dir"]
            updates.append("OLLAMA_MODELS")

        if "host" in config:
            os.environ["OLLAMA_HOST"] = config["host"]
            updates.append("OLLAMA_HOST")

        if "keep_alive" in config:
            os.environ["OLLAMA_KEEP_ALIVE"] = str(config["keep_alive"])
            updates.append("OLLAMA_KEEP_ALIVE")

        # Restart service to apply changes
        await self._restart_service()

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            details={"configured": updates},
        )

    async def uninstall(self) -> InstallResult:
        """Uninstall Ollama."""
        if self._is_windows:
            # Find uninstaller
            appdata = self._get_local_appdata_path("Programs", "Ollama")
            uninstaller = os.path.join(appdata, "Uninstall Ollama.exe")
            if os.path.exists(uninstaller):
                await self._run_command([uninstaller, "/S"], timeout=120)
        elif self._is_macos:
            app_path = "/Applications/Ollama.app"
            if os.path.exists(app_path):
                shutil.rmtree(app_path)
        elif self._is_linux:
            await self._run_command(
                ["sudo", "apt", "remove", "-y", "ollama"],
                timeout=120,
            )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def repair(self) -> InstallResult:
        """Repair Ollama installation."""
        logger.info("Repairing Ollama installation")

        # Stop service if running
        await self._stop_service()

        # Reinstall
        result = await self.install()

        # Start service
        if result.status == InstallStatus.INSTALLED:
            await self._start_service()

        return result

    async def _check_service_running(self) -> bool:
        """Check if Ollama service is running."""
        if self._is_windows:
            code, stdout, _ = await self._run_powershell(
                "Get-Process ollama -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"
            )
            return bool(stdout.strip())
        else:
            code, stdout, _ = await self._run_command(
                ["pgrep", "-x", "ollama"], timeout=10
            )
            return code == 0

    async def _test_api(self) -> bool:
        """Test Ollama API endpoint."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.OLLAMA_API_URL}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def _start_service(self) -> bool:
        """Start Ollama service."""
        if self._is_windows:
            code, _, _ = await self._run_command(
                ["net", "start", "ollama"], timeout=30
            )
            return code == 0
        else:
            code, _, _ = await self._run_command(
                ["ollama", "serve", "&"], timeout=10
            )
            return True

    async def _stop_service(self) -> bool:
        """Stop Ollama service."""
        if self._is_windows:
            code, _, _ = await self._run_command(
                ["net", "stop", "ollama"], timeout=30
            )
            return code == 0
        else:
            code, _, _ = await self._run_command(
                ["pkill", "ollama"], timeout=10
            )
            return code == 0

    async def _restart_service(self) -> bool:
        """Restart Ollama service."""
        await self._stop_service()
        await asyncio.sleep(2)
        return await self._start_service()

    def _get_common_paths(self) -> List[str]:
        """Get common Ollama install paths."""
        paths = []
        if self._is_windows:
            paths.extend([
                self._get_local_appdata_path("Programs", "Ollama", "ollama.exe"),
                os.path.expandvars(r"%USERPROFILE%\.ollama\ollama.exe"),
            ])
        elif self._is_macos:
            paths.extend([
                "/Applications/Ollama.app/Contents/MacOS/ollama",
                os.path.expanduser("~/.ollama/ollama"),
            ])
        else:
            paths.extend([
                "/usr/local/bin/ollama",
                "/usr/bin/ollama",
            ])
        return paths
