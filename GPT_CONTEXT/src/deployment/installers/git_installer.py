"""
Corax Orchestrator - Git Installer.

Production-oriented installer for Git version control.
Supports Windows (winget, direct installer) and macOS (brew).
"""

from typing import Dict, Any, List, Optional
import os

from src.deployment.installers.dev_base import DevInstallerBase
from src.deployment.installers.base import InstallResult, InstallStatus
from src.core.logging import get_logger

logger = get_logger(__name__)


class GitInstaller(DevInstallerBase):
    """Installer for Git version control system."""

    @property
    def tool_name(self) -> str:
        return "Git"

    @property
    def tool_key(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Distributed version control system"

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
            return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git")
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return "Git.Git"

    @property
    def brew_package(self) -> Optional[str]:
        return "git"

    @property
    def brew_cask(self) -> bool:
        return False

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://github.com/git-for-windows/git/releases/download/v2.48.1.windows.1/Git-2.48.1-64-bit.exe"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew

    @property
    def silent_flags_windows(self) -> List[str]:
        return ["/SILENT", "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["git"]

    @property
    def version_arguments(self) -> List[str]:
        return ["--version"]

    @property
    def path_entries(self) -> List[str]:
        if self._is_windows:
            git_path = self.install_dir
            if git_path:
                return [
                    os.path.join(git_path, "bin"),
                    os.path.join(git_path, "cmd"),
                    os.path.join(git_path, "mingw64", "bin"),
                ]
        return []

    @property
    def min_version(self) -> Optional[str]:
        return "2.30.0"

    def _parse_version(self, output: str) -> Optional[str]:
        """Parse git version from 'git version 2.48.1.windows.1'"""
        import re
        match = re.search(r'git version (\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        return super()._parse_version(output)
