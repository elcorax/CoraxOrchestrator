"""
Corax Orchestrator - Cross-Platform Abstraction Base.

Defines the abstract base class for all platform implementations,
providing a unified interface for OS-specific operations.
"""

import sys
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class PlatformType(Enum):
    """Supported platform types."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


class Architecture(Enum):
    """Supported CPU architectures."""
    X86_64 = "x86_64"
    ARM64 = "arm64"
    X86 = "x86"
    UNKNOWN = "unknown"


class PlatformInfo:
    """Container for detected platform information."""

    def __init__(
        self,
        platform_type: PlatformType,
        architecture: Architecture,
        os_version: str,
        hostname: str,
        is_admin: bool,
        is_wsl: bool = False,
        is_container: bool = False,
    ) -> None:
        self.platform_type = platform_type
        self.architecture = architecture
        self.os_version = os_version
        self.hostname = hostname
        self.is_admin = is_admin
        self.is_wsl = is_wsl
        self.is_container = is_container

    def to_dict(self) -> Dict[str, Any]:
        """Serialize platform info to dictionary."""
        return {
            "platform": self.platform_type.value,
            "architecture": self.architecture.value,
            "os_version": self.os_version,
            "hostname": self.hostname,
            "is_admin": self.is_admin,
            "is_wsl": self.is_wsl,
            "is_container": self.is_container,
        }


class PlatformBase(ABC):
    """
    Abstract base class for platform-specific implementations.

    All platform-specific operations (command execution, path resolution,
    permission checks, etc.) are abstracted through this interface.
    """

    def __init__(self) -> None:
        self._platform_info: Optional[PlatformInfo] = None

    @abstractmethod
    def detect(self) -> PlatformInfo:
        """Detect and return platform information."""
        ...

    @abstractmethod
    async def run_command(
        self,
        command: str,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        as_admin: bool = False,
    ) -> Tuple[int, str, str]:
        """
        Run a command on the platform.

        Args:
            command: The command to run
            args: Optional list of arguments
            cwd: Working directory
            env: Environment variables
            timeout: Timeout in seconds
            as_admin: Whether to run with elevated privileges

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        ...

    @abstractmethod
    def get_default_install_dir(self) -> Path:
        """Get the default installation directory for tools."""
        ...

    @abstractmethod
    def get_downloads_dir(self) -> Path:
        """Get the user's downloads directory."""
        ...

    @abstractmethod
    def get_temp_dir(self) -> Path:
        """Get the system temp directory."""
        ...

    @abstractmethod
    def get_appdata_dir(self) -> Path:
        """Get the application data directory."""
        ...

    @abstractmethod
    def get_config_dir(self) -> Path:
        """Get the configuration directory."""
        ...

    @abstractmethod
    def is_admin(self) -> bool:
        """Check if the current process has admin/root privileges."""
        ...

    @abstractmethod
    def is_process_running(self, name: str) -> bool:
        """Check if a process with the given name is running."""
        ...

    @abstractmethod
    def get_path_separator(self) -> str:
        """Get the platform path separator."""
        ...

    @abstractmethod
    def get_environment_variable(self, name: str) -> Optional[str]:
        """Get an environment variable."""
        ...

    @abstractmethod
    def set_environment_variable(
        self, name: str, value: str, persistent: bool = False
    ) -> bool:
        """Set an environment variable, optionally persistently."""
        ...

    @abstractmethod
    def get_shell_name(self) -> str:
        """Get the name of the default shell."""
        ...

    @abstractmethod
    def get_shell_command(self) -> str:
        """Get the command to invoke the default shell."""
        ...

    @abstractmethod
    def get_package_manager(self) -> Optional[str]:
        """Get the system package manager, if available."""
        ...

    @abstractmethod
    def get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information."""
        ...

    @abstractmethod
    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information."""
        ...

    @abstractmethod
    def get_disk_info(self) -> List[Dict[str, Any]]:
        """Get disk information."""
        ...

    @abstractmethod
    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Get GPU information."""
        ...

    @abstractmethod
    def get_network_info(self) -> Dict[str, Any]:
        """Get network information."""
        ...

    @abstractmethod
    def get_installed_software(self) -> List[Dict[str, str]]:
        """Get list of installed software."""
        ...

    @abstractmethod
    def open_file_explorer(self, path: Path) -> None:
        """Open file explorer at the given path."""
        ...

    @abstractmethod
    def open_terminal(self, cwd: Optional[Path] = None) -> None:
        """Open a terminal window."""
        ...

    @abstractmethod
    def open_url(self, url: str) -> None:
        """Open a URL in the default browser."""
        ...

    @property
    def platform_info(self) -> PlatformInfo:
        """Get cached platform info, detecting if necessary."""
        if self._platform_info is None:
            self._platform_info = self.detect()
        return self._platform_info


def detect_current_platform() -> PlatformType:
    """Detect the current operating system platform."""
    import platform as _platform
    system = _platform.system().lower()
    if system == "windows":
        return PlatformType.WINDOWS
    elif system == "darwin":
        return PlatformType.MACOS
    elif system == "linux":
        return PlatformType.LINUX
    return PlatformType.UNKNOWN


def detect_architecture() -> Architecture:
    """Detect the CPU architecture."""
    import platform as _platform
    machine = _platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        return Architecture.X86_64
    elif machine in ("arm64", "aarch64"):
        return Architecture.ARM64
    elif machine in ("i386", "i686", "x86"):
        return Architecture.X86
    return Architecture.UNKNOWN
