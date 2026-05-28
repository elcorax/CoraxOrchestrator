"""
Corax Orchestrator - macOS Platform Implementation.

Provides macOS-specific implementations for all platform operations,
including Bash/Zsh integration and Apple Silicon detection.
"""

import os
import sys
# Use stdlib platform explicitly to avoid shadowing by src.platform package
import platform as _stdlib_platform
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


class MacOSPlatform(PlatformBase):
    """macOS platform implementation."""

    def detect(self) -> PlatformInfo:
        """Detect macOS platform information."""
        return PlatformInfo(
            platform_type=PlatformType.MACOS,
            architecture=detect_architecture(),
            os_version=_stdlib_platform.version(),
            hostname=_stdlib_platform.node(),
            is_admin=self.is_admin(),
            is_wsl=False,
            is_container=self._is_container(),
        )

    def _is_container(self) -> bool:
        """Check if running inside a container."""
        try:
            result = subprocess.run(
                ["cat", "/proc/1/cgroup"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "docker" in result.stdout
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
        """Run a command on macOS."""
        if as_admin:
            full_command = ["sudo", command]
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
        return Path("/Applications")

    def get_downloads_dir(self) -> Path:
        """Get downloads directory."""
        return Path.home() / "Downloads"

    def get_temp_dir(self) -> Path:
        """Get temp directory."""
        return Path("/tmp")

    def get_appdata_dir(self) -> Path:
        """Get appdata directory."""
        return Path.home() / "Library" / "Application Support"

    def get_config_dir(self) -> Path:
        """Get config directory."""
        return Path.home() / "Library" / "Preferences"

    def is_admin(self) -> bool:
        """Check if running as root."""
        return os.geteuid() == 0

    def is_process_running(self, name: str) -> bool:
        """Check if a process is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_path_separator(self) -> str:
        """Get path separator."""
        return "/"

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
                shell_rc = Path.home() / ".zshrc"
                if not shell_rc.exists():
                    shell_rc = Path.home() / ".bash_profile"
                with open(shell_rc, "a") as f:
                    f.write(f'\nexport {name}="{value}"\n')
                return True
            except Exception as e:
                logger.error("Failed to set persistent env var", error=str(e))
                return False
        return True

    def get_shell_name(self) -> str:
        """Get shell name."""
        return os.environ.get("SHELL", "/bin/zsh").split("/")[-1]

    def get_shell_command(self) -> str:
        """Get shell command."""
        return os.environ.get("SHELL", "/bin/zsh")

    def get_package_manager(self) -> Optional[str]:
        """Get package manager."""
        for pm in ["brew", "port", "macports"]:
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
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            name = result.stdout.strip()
        except Exception:
            name = _stdlib_platform.processor()

        return {
            "name": name,
            "cores": psutil.cpu_count(logical=False),
            "logical_processors": psutil.cpu_count(logical=True),
            "max_clock_speed_mhz": None,
            "architecture": _stdlib_platform.machine(),
            "manufacturer": "Apple" if "Apple" in name else "Intel",
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
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            import json
            data = json.loads(result.stdout)
            for gpu in data.get("SPDisplaysDataType", []):
                gpus.append({
                    "name": gpu.get("sppci_model", "Unknown"),
                    "chipset": gpu.get("sppci_device", ""),
                    "vram_mb": gpu.get("spdisplays_vram", ""),
                    "metal_support": gpu.get("spdisplays_metal", ""),
                })
        except Exception as e:
            logger.warning("GPU detection failed", error=str(e))
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
        """Get installed software."""
        software = []
        # Check /Applications directory
        apps_dir = Path("/Applications")
        if apps_dir.exists():
            for app in apps_dir.iterdir():
                if app.suffix == ".app":
                    software.append({
                        "name": app.stem,
                        "path": str(app),
                        "install_source": "applications_folder",
                    })
        return software

    def open_file_explorer(self, path: Path) -> None:
        """Open Finder."""
        subprocess.Popen(["open", str(path)])

    def open_terminal(self, cwd: Optional[Path] = None) -> None:
        """Open Terminal."""
        cmd = ["open", "-a", "Terminal"]
        if cwd:
            cmd.extend([str(cwd)])
        subprocess.Popen(cmd)

    def open_url(self, url: str) -> None:
        """Open URL in browser."""
        import webbrowser
        webbrowser.open(url)
