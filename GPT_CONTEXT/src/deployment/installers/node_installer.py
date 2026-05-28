"""
Corax Orchestrator - Node.js Installer.

Production-oriented installer for Node.js runtime.
Supports Windows (winget, direct installer) and macOS (brew).
"""

from typing import Dict, Any, List, Optional
import os
import re

from src.deployment.installers.dev_base import DevInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class NodeInstaller(DevInstallerBase):
    """Installer for Node.js runtime."""

    @property
    def tool_name(self) -> str:
        return "Node.js"

    @property
    def tool_key(self) -> str:
        return "nodejs"

    @property
    def description(self) -> str:
        return "JavaScript runtime built on Chrome's V8 engine"

    @property
    def default_port(self) -> Optional[int]:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 1

    @property
    def dependencies(self) -> List[str]:
        return []

    @property
    def install_dir(self) -> Optional[str]:
        if self._is_windows:
            return os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs"
            )
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return "OpenJS.NodeJS.LTS"

    @property
    def brew_package(self) -> Optional[str]:
        return "node@22"

    @property
    def brew_cask(self) -> bool:
        return False

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew

    @property
    def silent_flags_windows(self) -> List[str]:
        return ["/quiet", "/norestart"]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["node"]

    @property
    def version_arguments(self) -> List[str]:
        return ["--version"]

    @property
    def path_entries(self) -> List[str]:
        if self._is_windows:
            install_dir = self.install_dir
            if install_dir:
                return [install_dir]
        return []

    @property
    def min_version(self) -> Optional[str]:
        return "18.0.0"

    def _parse_version(self, output: str) -> Optional[str]:
        """Parse Node.js version from 'v22.14.0'"""
        match = re.search(r'v?(\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        return super()._parse_version(output)

    async def get_npm_version(self) -> Optional[str]:
        """Get the installed npm version."""
        exit_code, stdout, stderr = await self._run_command(
            ["npm", "--version"], timeout=30
        )
        if exit_code == 0:
            return stdout.strip()
        return None

    async def verify(self) -> "InstallResult":
        """Verify Node.js installation and npm availability."""
        from src.deployment.installers.base import InstallResult, InstallStatus

        result = await super().verify()
        if result.status == InstallStatus.INSTALLED:
            npm_version = await self.get_npm_version()
            result.details["npm_version"] = npm_version
            result.details["npm_available"] = npm_version is not None
        return result
