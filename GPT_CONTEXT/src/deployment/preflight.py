"""
Corax Orchestrator - Environment Preflight Validator.

Validates the target machine environment before deployment,
detects missing runtimes, checks dependencies, and provides
actionable repair guidance for clean-machine execution.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PreflightResult:
    """Result of environment preflight validation."""

    success: bool = False
    python_ok: bool = False
    pip_ok: bool = False
    git_ok: bool = False
    node_ok: bool = False
    docker_ok: bool = False
    powershell_ok: bool = False
    admin_ok: bool = False
    disk_space_ok: bool = False
    memory_ok: bool = False
    network_ok: bool = False
    venv_ok: bool = False
    antivirus_detected: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    missing_runtimes: List[str] = field(default_factory=list)
    detected_antivirus: List[str] = field(default_factory=list)
    python_version: str = ""
    os_info: str = ""
    total_disk_gb: float = 0.0
    free_disk_gb: float = 0.0
    total_ram_gb: float = 0.0
    available_ram_gb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "python_ok": self.python_ok,
            "pip_ok": self.pip_ok,
            "git_ok": self.git_ok,
            "node_ok": self.node_ok,
            "docker_ok": self.docker_ok,
            "powershell_ok": self.powershell_ok,
            "admin_ok": self.admin_ok,
            "disk_space_ok": self.disk_space_ok,
            "memory_ok": self.memory_ok,
            "network_ok": self.network_ok,
            "venv_ok": self.venv_ok,
            "antivirus_detected": self.antivirus_detected,
            "errors": self.errors,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "missing_runtimes": self.missing_runtimes,
            "detected_antivirus": self.detected_antivirus,
            "python_version": self.python_version,
            "os_info": self.os_info,
            "total_disk_gb": self.total_disk_gb,
            "free_disk_gb": self.free_disk_gb,
            "total_ram_gb": self.total_ram_gb,
            "available_ram_gb": self.available_ram_gb,
        }


class EnvironmentPreflight:
    """
    Validates target machine environment before deployment.

    Checks:
    - Python runtime availability and version
    - pip availability
    - Git availability
    - Node.js availability
    - Docker availability
    - PowerShell availability
    - Administrator privileges
    - Disk space
    - Memory
    - Network connectivity
    - Virtual environment status
    - Antivirus detection
    """

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = Path(project_root or os.getcwd())

    def validate(self) -> PreflightResult:
        """Run complete environment preflight validation."""
        result = PreflightResult()
        try:
            import platform as _platform
            result.os_info = f"{_platform.system()} {_platform.release()} ({_platform.machine()})"
        except Exception:
            result.os_info = f"{sys.platform} unknown"


        # 1. Python
        self._check_python(result)

        # 2. pip
        self._check_pip(result)

        # 3. Git
        self._check_git(result)

        # 4. Node.js
        self._check_node(result)

        # 5. Docker
        self._check_docker(result)

        # 6. PowerShell (Windows)
        self._check_powershell(result)

        # 7. Administrator
        self._check_admin(result)

        # 8. Disk space
        self._check_disk(result)

        # 9. Memory
        self._check_memory(result)

        # 10. Network
        self._check_network(result)

        # 11. Virtual environment
        self._check_venv(result)

        # 12. Antivirus
        self._check_antivirus(result)

        # Determine overall success
        critical = [
            result.python_ok,
            result.pip_ok,
            result.disk_space_ok,
            result.memory_ok,
        ]
        result.success = all(critical)

        # Generate recommendations
        self._generate_recommendations(result)

        return result

    def _check_python(self, result: PreflightResult) -> None:
        """Check Python availability and version."""
        try:
            import platform as _platform
            result.python_version = _platform.python_version()
            version_tuple = tuple(int(x) for x in result.python_version.split(".")[:2])
            result.python_ok = version_tuple >= (3, 10)
            if not result.python_ok:
                result.errors.append(
                    f"Python {result.python_version} detected, need 3.10+"
                )
                result.missing_runtimes.append("python>=3.10")
        except Exception as e:
            result.errors.append(f"Python check failed: {e}")
            result.missing_runtimes.append("python")

    def _check_pip(self, result: PreflightResult) -> None:
        """Check pip availability."""
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            result.pip_ok = True
        except Exception:
            result.errors.append("pip not available")
            result.missing_runtimes.append("pip")

    def _check_git(self, result: PreflightResult) -> None:
        """Check Git availability."""
        git_path = shutil.which("git")
        if git_path:
            try:
                version = subprocess.run(
                    [git_path, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                result.git_ok = True
            except Exception:
                pass
        if not result.git_ok:
            result.warnings.append("Git not found (optional for most operations)")
            result.missing_runtimes.append("git")

    def _check_node(self, result: PreflightResult) -> None:
        """Check Node.js availability."""
        node_path = shutil.which("node")
        if node_path:
            try:
                version = subprocess.run(
                    [node_path, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                result.node_ok = True
            except Exception:
                pass
        if not result.node_ok:
            result.warnings.append("Node.js not found (optional for most operations)")

    def _check_docker(self, result: PreflightResult) -> None:
        """Check Docker availability."""
        docker_path = shutil.which("docker")
        if docker_path:
            try:
                version = subprocess.run(
                    [docker_path, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                result.docker_ok = True
            except Exception:
                pass

    def _check_powershell(self, result: PreflightResult) -> None:
        """Check PowerShell availability."""
        ps_path = shutil.which("powershell") or shutil.which("pwsh")
        if ps_path:
            try:
                version = subprocess.run(
                    [ps_path, "-Command", "$PSVersionTable.PSVersion"],
                    capture_output=True, text=True, timeout=5,
                )
                result.powershell_ok = True
            except Exception:
                pass
        if not result.powershell_ok and sys.platform == "win32":
            result.warnings.append("PowerShell not found on Windows")

    def _check_admin(self, result: PreflightResult) -> None:
        """Check administrator privileges."""
        try:
            if sys.platform == "win32":
                import ctypes
                result.admin_ok = ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                result.admin_ok = os.geteuid() == 0
        except Exception:
            result.admin_ok = False

        if not result.admin_ok:
            result.warnings.append(
                "Not running as administrator - some installations may fail"
            )

    def _check_disk(self, result: PreflightResult) -> None:
        """Check available disk space."""
        try:
            import psutil
            usage = psutil.disk_usage(str(self._project_root))

            result.total_disk_gb = round(usage.total / (1024**3), 2)
            result.free_disk_gb = round(usage.free / (1024**3), 2)
            # Require at least 10GB free
            result.disk_space_ok = usage.free > 10 * (1024**3)
            if not result.disk_space_ok:
                result.errors.append(
                    f"Insufficient disk space: {result.free_disk_gb:.1f}GB free "
                    f"(need 10GB+)"
                )
        except ImportError:
            result.warnings.append("psutil not available, disk check skipped")
            result.disk_space_ok = True  # Assume OK

    def _check_memory(self, result: PreflightResult) -> None:
        """Check available memory."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            result.total_ram_gb = round(mem.total / (1024**3), 2)
            result.available_ram_gb = round(mem.available / (1024**3), 2)
            # Require at least 4GB available
            result.memory_ok = mem.available > 4 * (1024**3)
            if not result.memory_ok:
                result.errors.append(
                    f"Insufficient memory: {result.available_ram_gb:.1f}GB available "
                    f"(need 4GB+)"
                )
        except ImportError:
            result.warnings.append("psutil not available, memory check skipped")
            result.memory_ok = True  # Assume OK

    def _check_network(self, result: PreflightResult) -> None:
        """Check network connectivity."""
        import socket
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            result.network_ok = True
        except (OSError, socket.timeout):
            result.warnings.append(
                "Network connectivity check failed - offline mode may be needed"
            )

    def _check_venv(self, result: PreflightResult) -> None:
        """Check virtual environment status."""
        in_venv = sys.prefix != sys.base_prefix
        result.venv_ok = in_venv
        if not in_venv:
            result.warnings.append(
                "Not running in a virtual environment - dependency isolation recommended"
            )

    def _check_antivirus(self, result: PreflightResult) -> None:
        """Detect common antivirus software."""
        av_indicators = {
            "Windows Defender": ["MsMpEng.exe", "MsSense.exe"],
            "Norton": ["NortonSecurity.exe", "Norton.exe"],
            "McAfee": ["McAfee.exe", "McSvcHost.exe"],
            "Kaspersky": ["avp.exe", "kavfs.exe"],
            "Avast": ["avast.exe", "AvastSvc.exe"],
            "Bitdefender": ["bdagent.exe", "bdservicehost.exe"],
            "ESET": ["ekrn.exe", "egui.exe"],
            "Sophos": ["SophosUI.exe", "SophosFS.exe"],
            "Malwarebytes": ["mbam.exe", "MBAMService.exe"],
        }

        detected = []
        for name, processes in av_indicators.items():
            for proc in processes:
                try:
                    if sys.platform == "win32":
                        result_check = subprocess.run(
                            ["tasklist", "/FI", f"IMAGENAME eq {proc}"],
                            capture_output=True, text=True, timeout=5,
                        )
                        if proc.lower() in result_check.stdout.lower():
                            detected.append(name)
                            break
                except Exception:
                    continue

        if detected:
            result.antivirus_detected = True
            result.detected_antivirus = detected
            result.warnings.append(
                f"Antivirus detected: {', '.join(detected)} - "
                "may interfere with installations"
            )

    def _generate_recommendations(self, result: PreflightResult) -> None:
        """Generate actionable recommendations."""
        if not result.python_ok:
            result.recommendations.append(
                "Install Python 3.10+ from https://www.python.org/downloads/"
            )
        if not result.pip_ok:
            result.recommendations.append(
                "Ensure pip is installed: python -m ensurepip --upgrade"
            )
        if not result.admin_ok and sys.platform == "win32":
            result.recommendations.append(
                "Run as Administrator for best results"
            )
        if not result.disk_space_ok:
            result.recommendations.append(
                f"Free up disk space (need 10GB+, have {result.free_disk_gb:.1f}GB)"
            )
        if not result.memory_ok:
            result.recommendations.append(
                f"Close memory-intensive applications "
                f"(need 4GB available, have {result.available_ram_gb:.1f}GB)"
            )
        if not result.network_ok:
            result.recommendations.append(
                "Check internet connectivity or prepare offline installer cache"
            )
        if not result.venv_ok:
            result.recommendations.append(
                "Create and activate a virtual environment: "
                "python -m venv .venv && .venv\\Scripts\\activate"
            )
        if result.antivirus_detected:
            result.recommendations.append(
                "Add project directory to antivirus exclusions for smoother operation"
            )
