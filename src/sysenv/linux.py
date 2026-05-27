"""
Corax Orchestrator - Linux Platform Implementation.

Provides Linux-specific implementations for all platform operations,
including Bash integration and distro-specific package management.
"""

import os
import sys
import platform
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


class LinuxPlatform(PlatformBase):
    """Linux platform implementation."""

    def detect(self) -> PlatformInfo:
        """Detect Linux platform information."""
        is_wsl = False
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    is_wsl = True
        except (FileNotFoundError, OSError):
            pass

        return PlatformInfo(
            platform_type=PlatformType.LINUX,
            architecture=detect_architecture(),
            os_version=platform.version(),
            hostname=platform.node(),
            is_admin=self.is_admin(),
            is_wsl=is_wsl,
            is_container=self._is_container(),
        )

    def _is_container(self) -> bool:
        """Check if running inside a container."""
        try:
            with open("/proc/1/cgroup", "r") as f:
                return "docker" in f.read()
        except FileNotFoundError:
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
        """Run a command on Linux."""
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
        return Path("/usr/local")

    def get_downloads_dir(self) -> Path:
        """Get downloads directory."""
        return Path.home() / "Downloads"

    def get_temp_dir(self) -> Path:
        """Get temp directory."""
        return Path("/tmp")

    def get_appdata_dir(self) -> Path:
        """Get appdata directory."""
        return Path.home() / ".local" / "share"

    def get_config_dir(self) -> Path:
        """Get config directory."""
        return Path.home() / ".config"

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
                shell_rc = Path.home() / ".bashrc"
                if not shell_rc.exists():
                    shell_rc = Path.home() / ".profile"
                with open(shell_rc, "a") as f:
                    f.write(f'\nexport {name}="{value}"\n')
                return True
            except Exception as e:
                logger.error("Failed to set persistent env var", error=str(e))
                return False
        return True

    def get_shell_name(self) -> str:
        """Get shell name."""
        return os.environ.get("SHELL", "/bin/bash").split("/")[-1]

    def get_shell_command(self) -> str:
        """Get shell command."""
        return os.environ.get("SHELL", "/bin/bash")

    def get_package_manager(self) -> Optional[str]:
        """Get package manager."""
        for pm in ["apt-get", "dnf", "yum", "pacman", "zypper", "apk"]:
            try:
                subprocess.run(
                    ["which", pm],
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
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
            name = ""
            for line in cpuinfo.split("\n"):
                if "model name" in line:
                    name = line.split(":")[1].strip()
                    break
        except FileNotFoundError:
            name = platform.processor()

        return {
            "name": name,
            "cores": psutil.cpu_count(logical=False),
            "logical_processors": psutil.cpu_count(logical=True),
            "max_clock_speed_mhz": None,
            "architecture": platform.machine(),
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
            result = subprocess.run(
                ["lspci", "-v"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.split("\n"):
                if "VGA" in line or "3D" in line or "Display" in line:
                    gpus.append({"name": line.strip()})
        except Exception:
            logger.warning("GPU detection failed")
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
        # Check common install locations
        for bin_path in ["/usr/bin", "/usr/local/bin", "/opt"]:
            path = Path(bin_path)
            if path.exists():
                for item in path.iterdir():
                    if item.is_file() and not item.name.startswith("."):
                        software.append({
                            "name": item.name,
                            "path": str(item),
                            "install_source": "filesystem",
                        })
        return software

    def open_file_explorer(self, path: Path) -> None:
        """Open file manager."""
        subprocess.Popen(["xdg-open", str(path)])

    def open_terminal(self, cwd: Optional[Path] = None) -> None:
        """Open terminal."""
        cmd = ["x-terminal-emulator"]
        if cwd:
            cmd.extend(["--working-directory", str(cwd)])
        subprocess.Popen(cmd)

    def open_url(self, url: str) -> None:
        """Open URL in browser."""
        import webbrowser
        webbrowser.open(url)
