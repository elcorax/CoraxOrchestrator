"""
Corax Orchestrator - Python Installer.

Production-oriented installer for Python runtime.
Supports Windows (winget, direct installer) and macOS (brew).
"""

from typing import Dict, Any, List, Optional
import os
import re

from src.deployment.installers.dev_base import DevInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class PythonInstaller(DevInstallerBase):
    """Installer for Python runtime."""

    @property
    def tool_name(self) -> str:
        return "Python"

    @property
    def tool_key(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return "Python programming language runtime"

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
                "Programs", "Python",
            )
        return None

    @property
    def winget_id(self) -> Optional[str]:
        return "Python.Python.3.12"

    @property
    def brew_package(self) -> Optional[str]:
        return "python@3.12"

    @property
    def brew_cask(self) -> bool:
        return False

    @property
    def download_url_windows(self) -> Optional[str]:
        return "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"

    @property
    def download_url_macos(self) -> Optional[str]:
        return None  # Use brew

    @property
    def silent_flags_windows(self) -> List[str]:
        return [
            "/quiet", "/passive",
            "InstallAllUsers=0",
            "PrependPath=1",
            "Include_test=0",
            "Include_pip=1",
            "Include_tcltk=0",
            "Include_launcher=0",
        ]

    @property
    def verify_command(self) -> Optional[List[str]]:
        return ["python"]

    @property
    def version_arguments(self) -> List[str]:
        return ["--version"]

    @property
    def path_entries(self) -> List[str]:
        if self._is_windows:
            local_appdata = os.environ.get(
                "LOCALAPPDATA",
                os.path.expandvars(r"%USERPROFILE%\AppData\Local"),
            )
            return [
                os.path.join(local_appdata, "Programs", "Python", "Python312"),
                os.path.join(local_appdata, "Programs", "Python", "Python312", "Scripts"),
            ]
        return []

    @property
    def env_vars(self) -> Dict[str, str]:
        return {}

    @property
    def min_version(self) -> Optional[str]:
        return "3.10.0"

    def _parse_version(self, output: str) -> Optional[str]:
        """Parse Python version from 'Python 3.12.9'"""
        match = re.search(r'Python (\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        return super()._parse_version(output)

    async def get_pip_version(self) -> Optional[str]:
        """Get the installed pip version."""
        exit_code, stdout, stderr = await self._run_command(
            ["python", "-m", "pip", "--version"], timeout=30
        )
        if exit_code == 0:
            match = re.search(r'pip (\d+\.\d+\.\d+)', stdout)
            if match:
                return match.group(1)
        return None

    async def verify(self) -> "InstallResult":
        """Verify Python installation and pip availability."""
        from src.deployment.installers.base import InstallResult, InstallStatus

        result = await super().verify()
        if result.status == InstallStatus.INSTALLED:
            pip_version = await self.get_pip_version()
            result.details["pip_version"] = pip_version
            result.details["pip_available"] = pip_version is not None
        return result
