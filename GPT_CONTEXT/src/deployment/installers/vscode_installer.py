"""
Corax Orchestrator - VS Code Installer.

Production-oriented installer for Visual Studio Code.
Supports Windows (winget, direct installer) and macOS (brew cask).
"""

from typing import Dict, Any, List, Optional
import os
import re

from src.deployment.installers.dev_base import DevInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class VSCodeInstaller(DevInstallerBase):
    """Installer for Visual Studio Code."""

    @property
    def tool_name(self) -> str:
        return "Visual Studio Code"

    @property
    def tool_key(self) -> str:
        return "vscode"

    @property
    def description(self) -> str:
        return "Code editor optimized for building and debugging modern applications"

    @property
    def default_port(self) -> Optional[int]:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 2

    @property
    def dependencies(self) -> List[str]:
        return []

    @property
    def install_dir(self) -> Optional[str]:
        if self._is_windows:
            return os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                "Microsoft VS Code",
            )
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return "Microsoft.VisualStudioCode"

    @property
    def brew_package(self) -> Optional[str]:
        return "visual-studio-code"

    @property
    def brew_cask(self) -> bool:
        return True

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://update.code.visualstudio.com/latest/win32-x64-user/stable"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew cask

    @property
    def silent_flags_windows(self) -> List[str]:
        return ["/SILENT", "/VERYSILENT", "/NORESTART", "/MERGETASKS=!runcode"]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["code"]

    @property
    def version_arguments(self) -> List[str]:
        return ["--version"]

    @property
    def path_entries(self) -> List[str]:
        if self._is_windows:
            install_dir = self.install_dir
            if install_dir:
                return [install_dir, os.path.join(install_dir, "bin")]
        return []

    @property
    def min_version(self) -> Optional[str]:
        return None

    def _parse_version(self, output: str) -> Optional[str]:
        """Parse VS Code version from multiline output."""
        lines = output.strip().split("\n")
        if lines:
            match = re.search(r'(\d+\.\d+\.\d+)', lines[0])
            if match:
                return match.group(1)
        return super()._parse_version(output)

    async def get_installed_extensions(self) -> List[str]:
        """Get list of installed VS Code extensions."""
        exit_code, stdout, stderr = await self._run_command(
            ["code", "--list-extensions"], timeout=30
        )
        if exit_code == 0:
            return [line.strip() for line in stdout.split("\n") if line.strip()]
        return []

    async def install_extension(self, extension_id: str) -> bool:
        """Install a VS Code extension."""
        exit_code, _, _ = await self._run_command(
            ["code", "--install-extension", extension_id], timeout=60
        )
        return exit_code == 0
