"""
Corax Orchestrator - Docker Desktop Installer.

Production-oriented installer for Docker Desktop.
Supports Windows (winget, direct installer) and macOS (brew cask).
"""

from typing import Dict, Any, List, Optional
import os
import re

from src.deployment.installers.dev_base import DevInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class DockerInstaller(DevInstallerBase):
    """Installer for Docker Desktop."""

    @property
    def tool_name(self) -> str:
        return "Docker Desktop"

    @property
    def tool_key(self) -> str:
        return "docker"

    @property
    def description(self) -> str:
        return "Containerization platform for building and sharing applications"

    @property
    def default_port(self) -> Optional[int]:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 10

    @property
    def dependencies(self) -> List[str]:
        return []

    @property
    def install_dir(self) -> Optional[str]:
        if self._is_windows:
            return os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"), "Docker", "Docker"
            )
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return "Docker.DockerDesktop"

    @property
    def brew_package(self) -> Optional[str]:
        return "docker"

    @property
    def brew_cask(self) -> bool:
        return True

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://desktop.docker.com/win/stable/Docker%20Desktop%20Installer.exe"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew cask

    @property
    def silent_flags_windows(self) -> List[str]:
        return ["install", "--quiet", "--accept-license", "--backend=wsl-2"]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["docker"]

    @property
    def version_arguments(self) -> List[str]:
        return ["--version"]

    @property
    def path_entries(self) -> List[str]:
        if self._is_windows:
            install_dir = self.install_dir
            if install_dir:
                return [
                    install_dir,
                    os.path.join(
                        os.environ.get("ProgramFiles", r"C:\Program Files"),
                        "Docker", "Docker", "resources", "bin",
                    ),
                ]
        return []

    @property
    def min_version(self) -> Optional[str]:
        return "24.0.0"

    def _parse_version(self, output: str) -> Optional[str]:
        """Parse Docker version from 'Docker version 27.5.1, build ...'"""
        match = re.search(r'Docker version (\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        return super()._parse_version(output)

    async def _install_windows(self, config: Optional[Dict[str, Any]] = None) -> tuple:
        """Windows-specific installation for Docker Desktop."""
        if not self._win_utils:
            return (False, "Windows utilities not available")

        # Strategy 1: winget
        if self.winget_id:
            logger.info("Installing Docker Desktop via winget")
            exit_code, stdout, stderr = await self._win_utils.winget_install(
                self.winget_id, timeout=600
            )
            if exit_code == 0:
                return (True, "Installed via winget")
            if await self._win_utils.winget_list(self.winget_id):
                return (True, "Already installed (winget)")

        # Strategy 2: Direct download
        if self.download_url_windows:
            logger.info("Installing Docker Desktop via direct download")
            try:
                import tempfile
                dl_path = os.path.join(
                    tempfile.gettempdir(),
                    "DockerDesktopInstaller.exe",
                )

                # Download
                dl_cmd = [
                    "powershell.exe", "-NoProfile", "-Command",
                    f"Invoke-WebRequest -Uri '{self.download_url_windows}' -OutFile '{dl_path}' -UseBasicParsing",
                ]
                dl_exit, dl_out, dl_err = await self._run_command(dl_cmd, timeout=600)
                if dl_exit != 0:
                    return (False, f"Download failed: {dl_err[:200]}")

                # Run installer with silent flags
                exit_code, stdout, stderr = await self._win_utils.run_installer(
                    dl_path, silent_args=self.silent_flags_windows, timeout=600
                )

                if exit_code == 0:
                    return (True, "Docker Desktop installed successfully")

                # Docker installer may return non-zero even on success
                version = await self.get_installed_version()
                if version:
                    return (True, f"Docker Desktop installed (v{version})")

                return (False, f"Installer failed with exit code {exit_code}")

            except Exception as e:
                return (False, f"Docker install failed: {str(e)}")

        return (False, "No Windows install method available")

    async def check_daemon_running(self) -> bool:
        """Check if Docker daemon is running."""
        exit_code, _, _ = await self._run_command(
            ["docker", "info"], timeout=30
        )
        return exit_code == 0

    async def verify(self) -> "InstallResult":
        """Verify Docker installation and daemon status."""
        from src.deployment.installers.base import InstallResult, InstallStatus

        result = await super().verify()
        if result.status == InstallStatus.INSTALLED:
            daemon_running = await self.check_daemon_running()
            result.details["daemon_running"] = daemon_running

            if not daemon_running:
                result.details["warning"] = (
                    "Docker CLI is available but daemon is not running. "
                    "Start Docker Desktop manually."
                )
        return result
