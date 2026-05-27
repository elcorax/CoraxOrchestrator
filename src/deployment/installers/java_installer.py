"""
Corax Orchestrator - Java JDK Installer.

Production-oriented installer for Java JDK.
Supports Windows (winget, direct installer) and macOS (brew).
"""

from typing import Dict, Any, List, Optional
import os
import re

from src.deployment.installers.dev_base import DevInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class JavaInstaller(DevInstallerBase):
    """Installer for Java JDK."""

    @property
    def tool_name(self) -> str:
        return "Java JDK"

    @property
    def tool_key(self) -> str:
        return "java"

    @property
    def description(self) -> str:
        return "Java Development Kit for building Java applications"

    @property
    def default_port(self) -> Optional[int]:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 3

    @property
    def dependencies(self) -> List[str]:
        return []

    @property
    def install_dir(self) -> Optional[str]:
        if self._is_windows:
            return os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"), "Java"
            )
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return "Microsoft.OpenJDK.21"

    @property
    def brew_package(self) -> Optional[str]:
        return "openjdk@21"

    @property
    def brew_cask(self) -> bool:
        return False

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://aka.ms/download-jdk/microsoft-jdk-21.0.6-windows-x64.msi"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew

    @property
    def silent_flags_windows(self) -> List[str]:
        return ["/quiet", "/norestart"]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["java"]

    @property
    def version_arguments(self) -> List[str]:
        return ["-version"]

    @property
    def path_entries(self) -> List[str]:
        if self._is_windows:
            return [
                os.path.join(
                    os.environ.get("ProgramFiles", r"C:\Program Files"),
                    "Microsoft", "jdk-21.0.6", "bin",
                ),
            ]
        return []

    @property
    def env_vars(self) -> Dict[str, str]:
        if self._is_windows:
            java_home = os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                "Microsoft", "jdk-21.0.6",
            )
            return {"JAVA_HOME": java_home}
        return {}

    @property
    def min_version(self) -> Optional[str]:
        return "17.0.0"

    def _parse_version(self, output: str) -> Optional[str]:
        """Parse Java version from 'openjdk version "21.0.6" 2025-01-21'"""
        match = re.search(r'version "(\d+\.\d+\.\d+)"', output)
        if match:
            return match.group(1)
        match = re.search(r'version "(\d+)"', output)
        if match:
            return f"{match.group(1)}.0.0"
        return super()._parse_version(output)

    async def get_javac_version(self) -> Optional[str]:
        """Get the installed javac version."""
        exit_code, stdout, stderr = await self._run_command(
            ["javac", "-version"], timeout=30
        )
        if exit_code == 0:
            match = re.search(r'(\d+\.\d+\.\d+)', stdout or stderr)
            if match:
                return match.group(1)
        return None

    async def verify(self) -> "InstallResult":
        """Verify Java installation and javac availability."""
        from src.deployment.installers.base import InstallResult, InstallStatus

        result = await super().verify()
        if result.status == InstallStatus.INSTALLED:
            javac_version = await self.get_javac_version()
            result.details["javac_version"] = javac_version
            result.details["javac_available"] = javac_version is not None
            result.details["java_home"] = os.environ.get("JAVA_HOME", "")
        return result
