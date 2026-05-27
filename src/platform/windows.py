"""
Corax Orchestrator - Windows Platform Implementation.

Provides Windows-specific implementations for all platform operations,
including PowerShell integration, WMI queries, and registry access.
"""

import os
import sys
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import psutil

from src.platform.base import (
    PlatformBase,
    PlatformInfo,
    PlatformType,
    Architecture,
    detect_architecture,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class WindowsPlatform(PlatformBase):
    """Windows platform implementation."""

    def detect(self) -> PlatformInfo:
        """Detect Windows platform information."""
        import platform as _platform
        is_wsl = False
        try:
            # Check if running under WSL
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    is_wsl = True
        except (FileNotFoundError, OSError):
            pass

        return PlatformInfo(
            platform_type=PlatformType.WINDOWS,
            architecture=detect_architecture(),
            os_version=_platform.version(),
            hostname=_platform.node(),
            is_admin=self.is_admin(),
            is_wsl=is_wsl,
            is_container=self._is_container(),
        )

    def _is_container(self) -> bool:
        """Check if running inside a container."""
        try:
            result = subprocess.run(
                ["powershell", "-Command", "(Get-Process -Name 'containerd' -ErrorAction SilentlyContinue).Count -gt 0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() == "True"
        except Exception:
            return False

    async def run_command(
        self,
        command: str,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        as_admin: bool = False,
    ) -> Tuple[int, str, str]:
        """Run a command on Windows using PowerShell."""
        if as_admin:
            # Use PowerShell to elevate
            cmd_parts = [command]
            if args:
                cmd_parts.extend(args)
            cmd_str = " ".join(str(a) for a in cmd_parts)
            ps_command = (
                f'Start-Process -FilePath "{command}" '
                f'-ArgumentList "{ " ".join(str(a) for a in args or []) }" '
                f'-Verb RunAs -Wait'
            )
            full_command = ["powershell", "-Command", ps_command]
        else:
            full_command = [command]
            if args:
                full_command.extend(str(a) for a in args)

        try:
            process = await asyncio.create_subprocess_exec(
                *full_command,
                cwd=cwd,
                env={**os.environ, **(env or {})},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            return (
                process.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            if process:
                process.kill()
            return (-1, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return (-1, "", str(e))

    def get_default_install_dir(self) -> Path:
        """Get default install directory."""
        return Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))

    def get_downloads_dir(self) -> Path:
        """Get downloads directory."""
        return Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Downloads"

    def get_temp_dir(self) -> Path:
        """Get temp directory."""
        return Path(os.environ.get("TEMP", "C:\\Windows\\Temp"))

    def get_appdata_dir(self) -> Path:
        """Get appdata directory."""
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))

    def get_config_dir(self) -> Path:
        """Get config directory."""
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))

    def is_admin(self) -> bool:
        """Check if running as administrator."""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def is_process_running(self, name: str) -> bool:
        """Check if a process is running."""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return name.lower() in result.stdout.lower()
        except Exception:
            return False

    def get_path_separator(self) -> str:
        """Get path separator."""
        return "\\"

    def get_environment_variable(self, name: str) -> Optional[str]:
        """Get environment variable."""
        return os.environ.get(name)

    def set_environment_variable(
        self, name: str, value: str, persistent: bool = False
    ) -> bool:
        """Set environment variable."""
        os.environ[name] = value
        if persistent:
            try:
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        f'[Environment]::SetEnvironmentVariable("{name}", "{value}", "User")',
                    ],
                    capture_output=True,
                    timeout=10,
                )
                return True
            except Exception as e:
                logger.error("Failed to set persistent env var", error=str(e))
                return False
        return True

    def get_shell_name(self) -> str:
        """Get shell name."""
        return "PowerShell"

    def get_shell_command(self) -> str:
        """Get shell command."""
        return "powershell.exe"

    def get_package_manager(self) -> Optional[str]:
        """Get package manager."""
        # Check for winget, chocolatey, or scoop
        for pm in ["winget", "choco", "scoop"]:
            try:
                subprocess.run(
                    [pm, "--version"],
                    capture_output=True,
                    timeout=5,
                )
                return pm
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    def get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information."""
        try:
            import wmi  # type: ignore
            c = wmi.WMI()

            cpu = c.Win32_Processor()[0]
            return {
                "name": cpu.Name.strip(),
                "cores": cpu.NumberOfCores,
                "logical_processors": cpu.NumberOfLogicalProcessors,
                "max_clock_speed_mhz": cpu.MaxClockSpeed,
                "architecture": cpu.Architecture,
                "manufacturer": cpu.Manufacturer,
            }
        except ImportError:
            import platform as _platform
            return {
                "name": _platform.processor(),
                "logical_processors": psutil.cpu_count(logical=True),
                "max_clock_speed_mhz": None,
                "architecture": None,
                "manufacturer": None,
            }

    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information."""
        mem = psutil.virtual_memory()
        return {
            "total_bytes": mem.total,
            "available_bytes": mem.available,
            "used_bytes": mem.used,
            "percent_used": mem.percent,
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
        }

    def get_disk_info(self) -> List[Dict[str, Any]]:
        """Get disk information."""
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "percent_used": usage.percent,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                })
            except (PermissionError, OSError):
                continue
        return disks

    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Get GPU information."""
        gpus = []
        try:
            import wmi
            c = wmi.WMI()
            for gpu in c.Win32_VideoController():
                gpus.append({
                    "name": gpu.Name.strip(),
                    "driver_version": gpu.DriverVersion,
                    "memory_bytes": gpu.AdapterRAM or 0,
                    "memory_gb": round((gpu.AdapterRAM or 0) / (1024**3), 2),
                    "resolution": f"{gpu.CurrentHorizontalResolution}x{gpu.CurrentVerticalResolution}"
                    if gpu.CurrentHorizontalResolution else None,
                })
        except ImportError:
            logger.warning("wmi module not available, GPU detection limited")
        return gpus

    def get_network_info(self) -> Dict[str, Any]:
        """Get network information."""
        net = psutil.net_if_addrs()
        io = psutil.net_io_counters()
        return {
            "interfaces": {
                name: [
                    {
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "family": str(addr.family),
                    }
                    for addr in addrs
                ]
                for name, addrs in net.items()
            },
            "bytes_sent": io.bytes_sent,
            "bytes_received": io.bytes_recv,
        }

    def get_installed_software(self) -> List[Dict[str, str]]:
        """Get installed software from registry."""
        software = []
        registry_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        try:
            import winreg
            for reg_path in registry_paths:
                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, reg_path, 0,
                        winreg.KEY_READ
                    )
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(key, subkey_name)
                            try:
                                name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                                software.append({
                                    "name": name,
                                    "version": version,
                                    "install_source": "registry",
                                })
                            except OSError:
                                pass
                            finally:
                                winreg.CloseKey(subkey)
                        except OSError:
                            continue
                    winreg.CloseKey(key)
                except OSError:
                    continue
        except ImportError:
            logger.warning("winreg not available, software detection limited")
        return software

    def open_file_explorer(self, path: Path) -> None:
        """Open file explorer."""
        import subprocess
        subprocess.Popen(["explorer", str(path)])

    def open_terminal(self, cwd: Optional[Path] = None) -> None:
        """Open terminal."""
        cmd = ["start", "powershell"]
        if cwd:
            cmd.extend(["-WorkingDirectory", str(cwd)])
        subprocess.Popen(cmd, shell=True)

    def open_url(self, url: str) -> None:
        """Open URL in browser."""
        import webbrowser
        webbrowser.open(url)
