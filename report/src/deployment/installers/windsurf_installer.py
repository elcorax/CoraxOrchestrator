"""
Corax Orchestrator - Windsurf Installer.

Production-oriented installer for Windsurf IDE.
Supports Windows (direct installer) and macOS (brew cask).
"""

from typing import Dict, Any, List, Optional
import os
import re

from src.deployment.installers.dev_base import DevInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class WindsurfInstaller(DevInstallerBase):
    """Installer for Windsurf IDE by Codeium."""

    @property
    def tool_name(self) -> str:
        return "Windsurf"

    @property
    def tool_key(self) -> str:
        return "windsurf"

    @property
    def description(self) -> str:
        return "AI-powered IDE by Codeium with agentic AI capabilities"

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
                os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%USERPROFILE%\AppData\Local")),
                "Programs", "windsurf",
            )
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return None  # Not available on winget yet

    @property
    def brew_package(self) -> Optional[str]:
        return "windsurf"

    @property
    def brew_cask(self) -> bool:
        return True

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://windsurf-stable.codeium.com/download/win32/x64/latest"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew cask

    @property
    def silent_flags_windows(self) -> List[str]:
        return ["/SILENT", "/VERYSILENT", "/NORESTART"]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["windsurf"]

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
        """Parse Windsurf version."""
        lines = output.strip().split("\n")
        if lines:
            match = re.search(r'(\d+\.\d+\.\d+)', lines[0])
            if match:
                return match.group(1)
        return super()._parse_version(output)
