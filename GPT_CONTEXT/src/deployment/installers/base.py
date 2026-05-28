"""
Corax Orchestrator - AI Installer Base Class.

Provides the abstract base for all AI runtime installers.
Each installer handles detection, installation, verification,
configuration, and repair for a specific AI tool.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.core.logging import get_logger
from src.core.exceptions import InstallationError
from src.platform.factory import PlatformFactory

logger = get_logger(__name__)


class InstallStatus(Enum):
    """Status of an installation operation."""
    NOT_INSTALLED = "not_installed"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    NEEDS_REPAIR = "needs_repair"
    OUTDATED = "outdated"
    BLOCKED = "blocked"


@dataclass
class InstallResult:
    """Result of an installation operation."""
    tool_name: str
    status: InstallStatus
    version: Optional[str] = None
    install_path: Optional[str] = None
    config_path: Optional[str] = None
    port: Optional[int] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Reporting fields
    operation_id: Optional[str] = None
    command_executed: Optional[str] = None
    duration_ms: float = 0.0
    retry_attempts: int = 0
    exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "version": self.version,
            "install_path": self.install_path,
            "config_path": self.config_path,
            "port": self.port,
            "error": self.error,
            "details": self.details,
            "timestamp": self.timestamp,
            "operation_id": self.operation_id,
            "command_executed": self.command_executed,
            "duration_ms": round(self.duration_ms, 1),
            "retry_attempts": self.retry_attempts,
            "exit_code": self.exit_code,
        }


class AIInstallerBase(ABC):
    """
    Abstract base for AI runtime installers.

    Each installer implements:
    - detect() - Check if the tool is installed
    - install() - Install the tool
    - verify() - Verify installation success
    - configure() - Configure runtime settings
    - uninstall() - Remove the tool
    - repair() - Attempt to repair broken installation
    - get_status() - Get detailed installation status
    """

    def __init__(self) -> None:
        self._platform = PlatformFactory.create()
        self._platform_info = self._platform.detect()
        self._os_name = os.name
        self._system = platform.system().lower()
        self._is_windows = self._os_name == "nt"
        self._is_macos = self._system == "darwin"
        self._is_linux = self._system == "linux"

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Human-readable tool name."""
        ...

    @property
    @abstractmethod
    def tool_key(self) -> str:
        """Machine-readable tool key for config/registry."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        ...

    @property
    @abstractmethod
    def default_port(self) -> Optional[int]:
        """Default port the tool runs on, if applicable."""
        ...

    @property
    @abstractmethod
    def min_disk_gb(self) -> int:
        """Minimum disk space required in GB."""
        ...

    @property
    @abstractmethod
    def dependencies(self) -> List[str]:
        """List of tool keys this tool depends on."""
        ...

    @abstractmethod
    async def detect(self) -> InstallResult:
        """
        Detect if the tool is installed.

        Returns:
            InstallResult with current installation status
        """
        ...

    @abstractmethod
    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """
        Install the tool.

        Args:
            config: Optional installation configuration

        Returns:
            InstallResult with installation outcome
        """
        ...

    @abstractmethod
    async def verify(self) -> InstallResult:
        """
        Verify installation success.

        Returns:
            InstallResult with verification status
        """
        ...

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """
        Configure runtime settings.

        Args:
            config: Configuration settings

        Returns:
            InstallResult with configuration outcome
        """
        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            details={"message": "Configuration not implemented"},
        )

    async def uninstall(self) -> InstallResult:
        """
        Remove the tool.

        Returns:
            InstallResult with uninstall outcome
        """
        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
            details={"message": "Uninstall not implemented"},
        )

    async def repair(self) -> InstallResult:
        """
        Attempt to repair a broken installation.

        Returns:
            InstallResult with repair outcome
        """
        logger.info("Attempting repair", tool=self.tool_name)
        return await self.install()

    async def get_status(self) -> Dict[str, Any]:
        """
        Get detailed installation status.

        Returns:
            Dict with comprehensive status information
        """
        result = await self.detect()
        return {
            "tool_name": self.tool_name,
            "tool_key": self.tool_key,
            "status": result.status.value,
            "version": result.version,
            "install_path": result.install_path,
            "config_path": result.config_path,
            "port": result.port,
            "default_port": self.default_port,
            "dependencies": self.dependencies,
            "min_disk_gb": self.min_disk_gb,
        }

    # --- Utility Methods ---

    async def _run_command(
        self,
        command: List[str],
        timeout: int = 120,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """
        Run a command asynchronously.

        Args:
            command: Command and arguments
            timeout: Timeout in seconds
            env: Environment variables
            cwd: Working directory

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return (-1, "", f"Command timed out after {timeout}s")
        except FileNotFoundError:
            return (-2, "", f"Command not found: {command[0]}")
        except Exception as e:
            return (-3, "", str(e))
        finally:
            if proc:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                if proc.stderr:
                    try:
                        proc.stderr.close()
                    except Exception:
                        pass
                try:
                    await proc.wait()
                except Exception:
                    pass

    async def _run_powershell(
        self,
        script: str,
        timeout: int = 120,
    ) -> Tuple[int, str, str]:
        """Run a PowerShell script."""
        return await self._run_command(
            ["powershell.exe", "-NoProfile", "-Command", script],
            timeout=timeout,
        )

    async def _download_file(
        self,
        url: str,
        dest_path: str,
        timeout: int = 300,
    ) -> bool:
        """Download a file using PowerShell or curl."""
        proc = None
        try:
            if self._is_windows:
                cmd = [
                    "powershell.exe", "-NoProfile", "-Command",
                    f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest_path}' -UseBasicParsing",
                ]
            else:
                cmd = ["curl", "-fsSL", "-o", dest_path, url]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode == 0
        except Exception as e:
            logger.error("Download failed", url=url, error=str(e))
            return False
        finally:
            if proc:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                if proc.stderr:
                    try:
                        proc.stderr.close()
                    except Exception:
                        pass
                try:
                    await proc.wait()
                except Exception:
                    pass

    def _find_in_path(self, executable: str) -> Optional[str]:
        """Find an executable in PATH."""
        path = shutil.which(executable)
        return path

    def _get_program_files_path(self, *parts: str) -> str:
        """Get a path under Program Files."""
        if self._is_windows:
            base = os.environ.get("ProgramFiles", r"C:\Program Files")
            return os.path.join(base, *parts)
        elif self._is_macos:
            return os.path.join("/Applications", *parts)
        else:
            return os.path.join("/usr/local", *parts)

    def _get_local_appdata_path(self, *parts: str) -> str:
        """Get a path under Local AppData (Windows)."""
        if self._is_windows:
            base = os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%USERPROFILE%\AppData\Local"))
            return os.path.join(base, *parts)
        elif self._is_macos:
            return os.path.join(os.path.expanduser("~/Library/Application Support"), *parts)
        else:
            return os.path.join(os.path.expanduser("~/.local/share"), *parts)

    def _get_roaming_appdata_path(self, *parts: str) -> str:
        """Get a path under Roaming AppData (Windows)."""
        if self._is_windows:
            base = os.environ.get("APPDATA", os.path.expandvars(r"%USERPROFILE%\AppData\Roaming"))
            return os.path.join(base, *parts)
        elif self._is_macos:
            return os.path.join(os.path.expanduser("~/Library/Application Support"), *parts)
        else:
            return os.path.join(os.path.expanduser("~/.config"), *parts)

    def _check_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", port))
                return result != 0
        except Exception:
            return False

    def _get_architecture(self) -> str:
        """Get system architecture."""
        machine = platform.machine().lower()
        if "arm64" in machine or "aarch64" in machine:
            return "arm64"
        elif "amd64" in machine or "x86_64" in machine:
            return "x64"
        elif "86" in machine:
            return "x86"
        return machine
