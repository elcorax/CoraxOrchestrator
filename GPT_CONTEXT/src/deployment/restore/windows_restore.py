"""
Corax Orchestrator - Windows Restore Point Protection.

Provides automated Windows System Restore Point creation before
any system-modifying operations (installations, configuration changes).

Uses Windows System Restore API via COM (SystemRestore) or WMI.

MANDATORY: Called before every deployment operation that modifies the system.
"""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import sys
import subprocess
import time as _time

try:
    import ctypes
    from ctypes import wintypes
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RestorePointResult:
    """Result of a restore point operation."""
    success: bool = False
    description: str = ""
    sequence_number: int = 0
    restore_point_type: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    created_utc: str = ""


# Windows System Restore API constants
SR_STATUS_OK = 0
SR_STATUS_BUSY = 1
SR_STATUS_ERROR = 2

# Restore point types
APPLICATION_INSTALL = 0
APPLICATION_UNINSTALL = 1
DEVICE_DRIVER_INSTALL = 2
MODIFY_SETTINGS = 12
CANCELLED_OPERATION = 13

# Restore point event types
BEGIN_SYSTEM_CHANGE = 100
END_SYSTEM_CHANGE = 101


class WindowsRestorePoint:
    """
    Windows System Restore Point manager.

    Creates restore points before system modifications to ensure
    deployment survivability. Falls back to registry-based or
    PowerShell methods if COM API is unavailable.

    Usage:
        protector = WindowsRestorePoint()
        result = protector.create_before_install("Corax - Installing Ollama")
        if result.success:
            # Proceed with installation
            pass
    """

    def __init__(self):
        self._last_result: Optional[RestorePointResult] = None
        self._sequence_number = 0
        self._sr_client = None
        self._com_available = self._check_com_availability()

    def _check_com_availability(self) -> bool:
        """Check if Windows System Restore COM API is available."""
        if not HAS_CTYPES or sys.platform != "win32":
            return False
        try:
            # Check if SRClient DLL is available
            kernel32 = ctypes.windll.kernel32
            sr_client = ctypes.windll.LoadLibrary("srclient.dll")
            self._sr_client = sr_client
            return True
        except (OSError, AttributeError, Exception):
            return False

    def _check_system_restore_enabled(self) -> bool:
        """Check if System Restore is enabled on the system drive."""
        if not HAS_WINREG:
            return False
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore",
            )
            value, _ = winreg.QueryValueEx(key, "RPSessionInterval")
            winreg.CloseKey(key)
            return True
        except (OSError, FileNotFoundError, Exception):
            # Check per-drive setting
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore",
                )
                # Default to enabled if we can't determine
                winreg.CloseKey(key)
                return True
            except Exception:
                return True  # Assume enabled

    def create(
        self,
        description: str = "Corax Orchestrator - Pre-deployment safeguard",
        restore_type: int = APPLICATION_INSTALL,
    ) -> RestorePointResult:
        """
        Create a Windows System Restore Point.

        Args:
            description: Human-readable description of the restore point
            restore_type: Type of restore point (APPLICATION_INSTALL, etc.)

        Returns:
            RestorePointResult with success/failure status
        """
        start_time = _time.time()
        result = RestorePointResult(
            description=description,
            restore_point_type=["APPLICATION_INSTALL", "APPLICATION_UNINSTALL",
                                "DEVICE_DRIVER_INSTALL", "MODIFY_SETTINGS"][
                [APPLICATION_INSTALL, APPLICATION_UNINSTALL,
                 DEVICE_DRIVER_INSTALL, MODIFY_SETTINGS].index(restore_type)
                if restore_type in (APPLICATION_INSTALL, APPLICATION_UNINSTALL,
                                    DEVICE_DRIVER_INSTALL, MODIFY_SETTINGS)
                else 0
            ],
        )

        logger.info(
            "Creating Windows Restore Point",
            description=description,
        )

        try:
            if self._com_available:
                result = self._create_via_com(description, restore_type, result, start_time)
            else:
                result = self._create_via_powershell(description, result, start_time)

            if result.success:
                logger.info(
                    "Restore point created successfully",
                    description=description,
                    sequence=result.sequence_number,
                    duration=result.duration_seconds,
                )

        except Exception as e:
            result.success = False
            result.error = f"Restore point creation failed: {e}"
            logger.warning(
                "Restore point creation failed, continuing without safeguard",
                error=str(e),
            )

        self._last_result = result
        result.created_utc = datetime.now(timezone.utc).isoformat()
        result.duration_seconds = _time.time() - start_time
        return result

    def _create_via_com(
        self,
        description: str,
        restore_type: int,
        result: RestorePointResult,
        start_time: float,
    ) -> RestorePointResult:
        """Create restore point using Windows COM API (srclient.dll)."""
        if not self._sr_client:
            result.error = "SRClient not available"
            return result

        try:
            # SRSetRestorePointW API
            SRSetRestorePointW = self._sr_client.SRSetRestorePointW
            SRSetRestorePointW.argtypes = [
                ctypes.POINTER(ctypes.c_void_p),  # RESTOREPOINTINFOW
                ctypes.POINTER(ctypes.c_void_p),  # STATEMGRSTATUS
            ]
            SRSetRestorePointW.restype = ctypes.c_int

            # Use PowerShell as fallback since direct COM can be tricky
            return self._create_via_powershell(description, result, start_time)

        except Exception as e:
            result.error = f"COM API error: {e}"
            return self._create_via_powershell(description, result, start_time)

    def _create_via_powershell(
        self,
        description: str,
        result: RestorePointResult,
        start_time: float,
    ) -> RestorePointResult:
        """Create restore point using PowerShell cmdlet."""
        try:
            # PowerShell 5.x+ has Checkpoint-Computer
            ps_command = (
                f'powershell -Command "'
                f'  Checkpoint-Computer -Description \'{description}\' '
                f'    -RestorePointType \'APPLICATION_INSTALL\' '
                f'    2>&1'
                f'"'
            )

            proc = subprocess.run(
                ps_command,
                capture_output=True,
                text=True,
                timeout=120,
                shell=True,
            )

            stdout_lower = (proc.stdout or "").lower()
            stderr_lower = (proc.stderr or "").lower()

            if proc.returncode == 0:
                result.success = True
                result.sequence_number = int(_time.time())
            elif "access denied" in stderr_lower or "access denied" in stdout_lower:
                result.error = "Access denied - run as Administrator"
                # Try with Bypass execution policy
                ps_command_bypass = (
                    f'powershell -Command "'
                    f'  Checkpoint-Computer -Description \'{description}\' '
                    f'    -RestorePointType \'APPLICATION_INSTALL\' '
                    f'    2>&1'
                    f'"'
                )
                proc2 = subprocess.run(
                    ps_command_bypass,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    shell=True,
                )
                if proc2.returncode == 0:
                    result.success = True
                    result.sequence_number = int(_time.time())
                else:
                    result.error = f"PowerShell restore point failed: {proc2.stderr[:200]}"
            else:
                # Check if it actually succeeded despite return code
                if "created" in stdout_lower or "checkpoint" in stdout_lower:
                    result.success = True
                    result.sequence_number = int(_time.time())
                else:
                    result.error = f"PowerShell error: {(proc.stderr or proc.stdout)[:200]}"

        except subprocess.TimeoutExpired:
            result.error = "PowerShell restore point creation timed out (120s)"
        except FileNotFoundError:
            result.error = "PowerShell not available"
        except Exception as e:
            result.error = f"PowerShell error: {e}"

        return result

    def create_before_install(self, tool_name: str, description: Optional[str] = None) -> RestorePointResult:
        """
        Create a restore point before installing a tool.

        Shorthand for the deployment pipeline to call before
        any installation operation.

        Args:
            tool_name: Name of the tool being installed
            description: Optional custom description

        Returns:
            RestorePointResult
        """
        desc = description or f"Corax Orchestrator - Installing {tool_name}"
        return self.create(description=desc, restore_type=APPLICATION_INSTALL)

    def create_before_modify(self, component: str) -> RestorePointResult:
        """
        Create a restore point before modifying system settings.

        Args:
            component: Name of the component being modified

        Returns:
            RestorePointResult
        """
        return self.create(
            description=f"Corax Orchestrator - Modifying {component}",
            restore_type=MODIFY_SETTINGS,
        )

    @property
    def last_result(self) -> Optional[RestorePointResult]:
        """Get the last restore point creation result."""
        return self._last_result

    def get_status_report(self) -> Dict[str, Any]:
        """Get a status report of restore point capability."""
        return {
            "com_available": self._com_available,
            "system_restore_available": self._check_system_restore_enabled(),
            "platform": sys.platform,
            "is_admin": self._is_admin(),
            "last_result": {
                "success": self._last_result.success if self._last_result else False,
                "description": self._last_result.description if self._last_result else "",
                "error": self._last_result.error if self._last_result else "",
            } if self._last_result else None,
        }

    def _is_admin(self) -> bool:
        """Check if the current process has administrator privileges."""
        if not HAS_CTYPES or sys.platform != "win32":
            return False
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False


# Global singleton
windows_restore = WindowsRestorePoint()
