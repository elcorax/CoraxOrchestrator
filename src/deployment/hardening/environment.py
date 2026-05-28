"""
Corax Orchestrator — Environment Hardening Module.

Provides advanced environment validation before deployment operations:
- GPU detection (NVIDIA CUDA, AMD ROCm)
- WSL detection and version validation
- Windows feature validation (required roles/features)
- Disk space verification with reserved space checks
- Network connectivity validation
- Anti-virus interference detection
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EnvironmentHardeningResult:
    """Result from an environment hardening check."""
    passed: bool = False
    check_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "check_name": self.check_name,
            "details": self.details,
            "warnings": self.warnings,
            "errors": self.errors,
            "recommendations": self.recommendations,
            "duration_ms": round(self.duration_ms, 2),
        }


class EnvironmentHardening:
    """
    Validates and hardens the deployment environment before operations.

    Performs comprehensive environment checks including GPU availability,
    WSL state, Windows features, disk space, network connectivity, and
    potential anti-virus interference.

    Each check returns an EnvironmentHardeningResult with actionable insight.
    """

    MINIMUM_DISK_GB = 5.0
    RESERVED_DISK_GB = 1.0
    WSL_MIN_VERSION = 2

    def __init__(self):
        self._results: List[EnvironmentHardeningResult] = []
        self._system_info: Dict[str, Any] = {}

    def run_all_checks(self) -> List[EnvironmentHardeningResult]:
        """Run all environment hardening checks and return results."""
        self._collect_system_info()

        checks = [
            ("gpu", self.check_gpu),
            ("wsl", self.check_wsl),
            ("windows_features", self.check_windows_features),
            ("disk_space", self.check_disk_space),
            ("network", self.check_network),
            ("antivirus", self.check_antivirus_interference),
            ("python_env", self.check_python_environment),
            ("path_integrity", self.check_path_integrity),
        ]

        for name, check_fn in checks:
            try:
                result = check_fn()
                self._results.append(result)
                if not result.passed:
                    logger.warning(
                        f"Environment check failed: {name}",
                        errors=result.errors,
                        recommendations=result.recommendations,
                    )
            except Exception as e:
                logger.error(f"Environment check '{name}' raised exception: {e}")
                self._results.append(EnvironmentHardeningResult(
                    passed=False,
                    check_name=name,
                    errors=[f"Check raised exception: {e}"],
                    recommendations=["Review system compatibility"],
                ))

        return self._results

    def _collect_system_info(self) -> None:
        """Collect basic system information for context."""
        self._system_info = {
            "platform": platform.platform(),
            "platform_system": platform.system(),
            "platform_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "cwd": os.getcwd(),
        }

    # ------------------------------------------------------------------
    # GPU Detection
    # ------------------------------------------------------------------

    def check_gpu(self) -> EnvironmentHardeningResult:
        """
        Detect GPU hardware and compute capabilities.

        Checks for NVIDIA CUDA via nvidia-smi and AMD ROCm via rocminfo.
        Provides GPU model, driver version, VRAM, and compute capability info.
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="gpu")
        details: Dict[str, Any] = {
            "nvidia_cuda": False,
            "amd_rocm": False,
            "gpu_count": 0,
            "gpu_info": [],
        }
        warnings: List[str] = []
        recommendations: List[str] = []

        # Check NVIDIA GPU
        nvidia_info = self._detect_nvidia_gpu()
        if nvidia_info:
            details["nvidia_cuda"] = True
            details["gpu_count"] += len(nvidia_info)
            details["gpu_info"].extend(nvidia_info)
        else:
            warnings.append("No NVIDIA GPU detected via nvidia-smi")

        # Check AMD GPU
        amd_info = self._detect_amd_gpu()
        if amd_info:
            details["amd_rocm"] = True
            details["gpu_count"] += len(amd_info)
            details["gpu_info"].extend(amd_info)
        else:
            warnings.append("No AMD GPU detected via rocminfo")

        # Determine if GPU is available for AI workloads
        if details["gpu_count"] > 0:
            result.passed = True
            recommendations.append("GPU acceleration is available for AI models")
        else:
            result.passed = True  # Not a hard failure — CPU fallback is acceptable
            warnings.append(
                "No compatible GPU detected. AI models will run on CPU, "
                "which may be significantly slower."
            )
            recommendations.append(
                "Consider installing an NVIDIA GPU with CUDA support "
                "for optimal AI performance"
            )

        result.details = details
        result.warnings = warnings
        result.recommendations = recommendations
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    def _detect_nvidia_gpu(self) -> List[Dict[str, Any]]:
        """Detect NVIDIA GPU using nvidia-smi."""
        gpus = []
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return gpus

        try:
            proc = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=index,name,driver_version,memory.total,compute_cap",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                for line in proc.stdout.strip().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        gpu_info = {
                            "vendor": "NVIDIA",
                            "index": parts[0],
                            "name": parts[1],
                            "driver_version": parts[2] if len(parts) > 2 else "unknown",
                            "vram_total": parts[3] if len(parts) > 3 else "unknown",
                            "compute_capability": parts[4] if len(parts) > 4 else "unknown",
                        }
                        gpus.append(gpu_info)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug(f"nvidia-smi detection failed: {e}")

        return gpus

    def _detect_amd_gpu(self) -> List[Dict[str, Any]]:
        """Detect AMD GPU using rocminfo."""
        gpus = []
        rocminfo = shutil.which("rocminfo")
        if not rocminfo:
            return gpus

        try:
            proc = subprocess.run(
                [rocminfo],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                # Parse rocminfo output for GPU devices
                for line in proc.stdout.splitlines():
                    if "Name:" in line and "GPU" in line:
                        gpu_info = {
                            "vendor": "AMD",
                            "detected_via": "rocminfo",
                            "raw": line.strip(),
                        }
                        gpus.append(gpu_info)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug(f"rocminfo detection failed: {e}")

        return gpus

    # ------------------------------------------------------------------
    # WSL Detection
    # ------------------------------------------------------------------

    def check_wsl(self) -> EnvironmentHardeningResult:
        """
        Check Windows Subsystem for Linux availability and version.

        Validates WSL is installed, version >= 2, and at least one
        distribution is available for Docker/WSL-backed tooling.
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="wsl")
        details: Dict[str, Any] = {
            "wsl_installed": False,
            "wsl_version": None,
            "default_distribution": None,
            "distributions": [],
        }
        warnings: List[str] = []

        if platform.system() != "Windows":
            result.passed = True
            result.details = {"note": "WSL check skipped — not on Windows"}
            result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return result

        wsl = shutil.which("wsl")
        if not wsl:
            result.passed = True  # Not a hard failure
            result.details = details
            result.warnings = ["WSL is not installed. Docker Desktop will use Hyper-V backend."]
            result.recommendations = [
                "Install WSL 2 for better Docker performance: "
                "wsl --install"
            ]
            result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return result

        try:
            # Get WSL version
            proc_ver = subprocess.run(
                [wsl, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc_ver.returncode == 0:
                ver_match = re.search(r"WSL version:\s+(\d+)", proc_ver.stdout)
                if ver_match:
                    details["wsl_version"] = int(ver_match.group(1))

            # List distributions
            proc_list = subprocess.run(
                [wsl, "--list", "--verbose"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc_list.returncode == 0:
                lines = proc_list.stdout.strip().splitlines()
                # Skip header line
                for line in lines[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        details["distributions"].append({
                            "name": parts[0],
                            "state": parts[1],
                            "version": parts[2],
                        })
                    elif len(parts) >= 1:
                        details["distributions"].append({"name": parts[0]})

                if details["distributions"]:
                    details["default_distribution"] = details["distributions"][0]["name"]

            details["wsl_installed"] = True
            wsl_version = details.get("wsl_version", 1)

            if wsl_version >= self.WSL_MIN_VERSION:
                result.passed = True
            else:
                result.passed = True  # Soft check
                warnings.append(
                    f"WSL version {wsl_version} detected. "
                    f"WSL {self.WSL_MIN_VERSION} is recommended."
                )
                result.recommendations.append(
                    f"Upgrade to WSL {self.WSL_MIN_VERSION} for better performance: "
                    "wsl --set-default-version 2"
                )

        except (subprocess.TimeoutExpired, OSError) as e:
            result.passed = True
            warnings.append(f"WSL detection encountered an error: {e}")

        result.details = details
        result.warnings = warnings
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # Windows Features
    # ------------------------------------------------------------------

    def check_windows_features(self) -> EnvironmentHardeningResult:
        """
        Check required Windows features for AI/deployment tooling.

        Validates:
        - Virtual Machine Platform (required for WSL 2, Docker)
        - Windows Subsystem for Linux
        - Hyper-V (optional, for Docker Desktop)
        - Containers feature
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="windows_features")
        details: Dict[str, Any] = {
            "features": {},
        }
        warnings: List[str] = []

        if platform.system() != "Windows":
            result.passed = True
            result.details = {"note": "Windows features check skipped — not on Windows"}
            result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return result

        required_features = [
            "VirtualMachinePlatform",
            "Microsoft-Windows-Subsystem-Linux",
        ]
        optional_features = [
            "Hyper-V",
            "Containers",
        ]

        dism = shutil.which("dism")
        if not dism:
            result.passed = True
            result.details = {"note": "DISM not available — cannot check Windows features"}
            result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return result

        try:
            proc = subprocess.run(
                [dism, "/Online", "/Get-FeatureInfo", "/FeatureName:VirtualMachinePlatform"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                enabled = "Enabled" in proc.stdout and "Disable" not in proc.stdout.split("State :")[-1:][0] if "State :" in proc.stdout else False
                details["features"]["VirtualMachinePlatform"] = {
                    "enabled": enabled,
                    "required": True,
                }
                if not enabled:
                    warnings.append("Virtual Machine Platform is not enabled")
                    result.recommendations.append(
                        "Enable Virtual Machine Platform:\n"
                        "  dism /Online /Enable-Feature /FeatureName:VirtualMachinePlatform /All"
                    )

            proc2 = subprocess.run(
                [dism, "/Online", "/Get-FeatureInfo", "/FeatureName:Microsoft-Windows-Subsystem-Linux"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc2.returncode == 0:
                enabled = "Enabled" in proc2.stdout
                details["features"]["Microsoft-Windows-Subsystem-Linux"] = {
                    "enabled": enabled,
                    "required": True,
                }
                if not enabled:
                    warnings.append("Windows Subsystem for Linux is not enabled")
                    result.recommendations.append(
                        "Enable WSL:\n"
                        "  dism /Online /Enable-Feature /FeatureName:Microsoft-Windows-Subsystem-Linux /All"
                    )

            # Check optional features
            for feat in optional_features:
                proc_opt = subprocess.run(
                    [dism, "/Online", "/Get-FeatureInfo", f"/FeatureName:{feat}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc_opt.returncode == 0:
                    enabled = "Enabled" in proc_opt.stdout
                    details["features"][feat] = {
                        "enabled": enabled,
                        "required": False,
                    }
                    if not enabled:
                        warnings.append(f"Optional feature '{feat}' is not enabled")

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(f"Windows features detection error: {e}")
            result.details = {"error": str(e)}

        all_required_enabled = all(
            v.get("enabled", False)
            for v in details["features"].values()
            if v.get("required", False)
        )
        result.passed = all_required_enabled
        result.details = details
        result.warnings = warnings
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # Disk Space
    # ------------------------------------------------------------------

    def check_disk_space(self) -> EnvironmentHardeningResult:
        """
        Check available disk space on the installation drive.

        Ensures at least MINIMUM_DISK_GB is free with RESERVED_DISK_GB
        as a safety buffer.
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="disk_space")
        install_drive = os.path.splitdrive(os.getcwd())[0] or "C:"

        try:
            usage = shutil.disk_usage(install_drive + "\\")
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)

            details = {
                "drive": install_drive,
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "minimum_required_gb": self.MINIMUM_DISK_GB,
                "reserved_buffer_gb": self.RESERVED_DISK_GB,
                "effective_free_gb": round(free_gb - self.RESERVED_DISK_GB, 2),
            }

            effective_free = free_gb - self.RESERVED_DISK_GB
            if effective_free >= self.MINIMUM_DISK_GB:
                result.passed = True
            elif effective_free >= 2.0:
                result.passed = True
                result.warnings = [
                    f"Low disk space on {install_drive}: {free_gb:.1f} GB free "
                    f"(minimum {self.MINIMUM_DISK_GB} GB recommended)"
                ]
                result.recommendations = [
                    "Free up disk space to ensure smooth operation",
                    "Consider cleaning temporary files",
                ]
            else:
                result.passed = False
                result.errors = [
                    f"Insufficient disk space on {install_drive}: "
                    f"{free_gb:.1f} GB free (need at least "
                    f"{self.MINIMUM_DISK_GB + self.RESERVED_DISK_GB} GB)"
                ]
                result.recommendations = [
                    "Free at least 5 GB of disk space before proceeding",
                    "Check for large files in Downloads, Temp, and Recycle Bin",
                    "Consider installing to a different drive with more space",
                ]

            result.details = details

        except Exception as e:
            result.passed = True  # Soft fail — we can still try
            result.warnings = [f"Could not check disk space: {e}"]
            result.details = {"error": str(e)}

        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # Network Connectivity
    # ------------------------------------------------------------------

    def check_network(self) -> EnvironmentHardeningResult:
        """
        Check network connectivity to essential endpoints.

        Tests connectivity to:
        - General internet (via HTTP check to known endpoints)
        - GitHub API (for tool downloads)
        - Hugging Face (for model downloads)
        - Docker Hub (for container images)
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="network")
        details: Dict[str, Any] = {
            "endpoints": {},
        }
        warnings: List[str] = []

        endpoints = {
            "internet": ("https://google.com", "General internet connectivity"),
            "github_api": ("https://api.github.com", "GitHub API (tool downloads)"),
            "huggingface": ("https://huggingface.co", "Hugging Face (model downloads)"),
            "docker_hub": ("https://hub.docker.com", "Docker Hub (container images)"),
            "pypi": ("https://pypi.org", "PyPI (Python packages)"),
        }

        all_reachable = True
        try:
            import urllib.request
            import ssl

            # Create an unverified SSL context for maximum compatibility
            ssl_ctx = ssl._create_unverified_context()

            for name, (url, description) in endpoints.items():
                try:
                    req = urllib.request.Request(url, method="HEAD")
                    resp = urllib.request.urlopen(
                        req, timeout=10, context=ssl_ctx
                    )
                    reachable = resp.status < 500
                    details["endpoints"][name] = {
                        "reachable": reachable,
                        "status": resp.status,
                        "description": description,
                    }
                    if not reachable:
                        all_reachable = False
                        warnings.append(f"Endpoint {name} returned status {resp.status}")
                except Exception as e:
                    details["endpoints"][name] = {
                        "reachable": False,
                        "error": str(e),
                        "description": description,
                    }
                    all_reachable = False
                    warnings.append(f"Cannot reach {name}: {e}")

        except ImportError:
            # Fallback: use socket check
            import socket
            for name, (url, description) in endpoints.items():
                try:
                    hostname = url.split("//")[1].split("/")[0]
                    socket.create_connection((hostname, 443), timeout=10)
                    details["endpoints"][name] = {
                        "reachable": True,
                        "description": description,
                    }
                except Exception as e:
                    details["endpoints"][name] = {
                        "reachable": False,
                        "error": str(e),
                        "description": description,
                    }
                    all_reachable = False

        result.passed = all_reachable
        if not all_reachable:
            result.warnings = warnings
            result.recommendations = [
                "Check your internet connection",
                "Verify firewall/proxy settings are not blocking required endpoints",
                "Some features may require offline installation methods",
            ]

        result.details = details
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # Anti-Virus Interference Detection
    # ------------------------------------------------------------------

    def check_antivirus_interference(self) -> EnvironmentHardeningResult:
        """
        Detect potential anti-virus interference with deployments.

        Checks for:
        - Windows Defender real-time monitoring status
        - Common AV software processes
        - Temp directory exclusions
        - Known AV interference patterns
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="antivirus")
        details: Dict[str, Any] = {
            "windows_defender_enabled": None,
            "av_processes_found": [],
            "temp_excluded": None,
            "potential_interference": False,
        }
        recommendations: List[str] = []

        # Check Windows Defender status via PowerShell
        if platform.system() == "Windows":
            try:
                proc = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "Get-MpPreference | Select-Object -Property DisableRealtimeMonitoring | Format-List",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if proc.returncode == 0:
                    disabled = "True" in proc.stdout and "False" not in proc.stdout
                    details["windows_defender_enabled"] = not disabled
                    if not disabled:
                        details["potential_interference"] = True
                        recommendations.append(
                            "Consider adding deployment directories to Windows Defender exclusions"
                        )
            except Exception as e:
                logger.debug(f"Windows Defender check failed: {e}")

        # Check for common AV processes
        av_processes = [
            "MsMpEng.exe",   # Windows Defender
            "avguard.exe",   # Avira
            "avp.exe",       # Kaspersky
            "egui.exe",      # ESET
            "mcshield.exe",  # McAfee
            "savservice.exe", # Sophos
            "bdservicehost.exe", # Bitdefender
            "norton.exe",    # Norton
            "ccSvcHst.exe",  # Norton
            "avgrsx.exe",    # AVG
            "avastsvc.exe",  # Avast
        ]

        try:
            proc_tasklist = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc_tasklist.returncode == 0:
                for line in proc_tasklist.stdout.splitlines():
                    for av in av_processes:
                        if av.lower() in line.lower():
                            details["av_processes_found"].append(av)
                            details["potential_interference"] = True
                            break
        except Exception as e:
            logger.debug(f"AV process detection failed: {e}")

        # Check if temp directory is excluded from AV scanning
        temp_dir = tempfile.gettempdir() if "tempfile" in dir() else os.environ.get("TEMP", "")
        if temp_dir and platform.system() == "Windows":
            try:
                proc = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        f"Get-MpPreference | Select-Object -ExpandProperty ExclusionPath",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if proc.returncode == 0:
                    excluded_paths = [
                        p.strip() for p in proc.stdout.splitlines()
                        if p.strip() and not p.startswith("PS")
                    ]
                    details["temp_excluded"] = temp_dir in excluded_paths
                    if not details.get("temp_excluded", False) and details.get("potential_interference"):
                        recommendations.append(
                            "Add the following directory to AV exclusions:\n"
                            f"  {temp_dir}"
                        )
            except Exception:
                pass

        result.passed = True  # Advisory check — not a blocker
        result.details = details
        result.recommendations = recommendations
        if details.get("potential_interference"):
            result.warnings = [
                "Anti-virus software may interfere with deployments",
                "Consider adding exclusions for Corax deployment directories",
            ]
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # Python Environment
    # ------------------------------------------------------------------

    def check_python_environment(self) -> EnvironmentHardeningResult:
        """
        Validate the Python environment for deployment operations.

        Checks:
        - Python version >= 3.8
        - Virtual environment active
        - pip availability
        - Critical dependencies installed
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="python_env")
        details: Dict[str, Any] = {
            "python_version": sys.version,
            "venv_active": hasattr(sys, "real_prefix") or (
                hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
            ),
            "pip_available": False,
            "key_packages": {},
        }
        warnings: List[str] = []

        # Python version check
        py_version = sys.version_info
        if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 8):
            result.passed = False
            result.errors = [
                f"Python {py_version.major}.{py_version.minor} is too old. "
                "Python 3.8+ is required."
            ]
            result.recommendations = [
                "Install Python 3.8 or later from https://python.org"
            ]
        else:
            result.passed = True

        # Pip availability
        pip_path = shutil.which("pip")
        if pip_path:
            details["pip_available"] = True
            try:
                proc = subprocess.run(
                    [pip_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode == 0:
                    details["pip_version"] = proc.stdout.strip()
            except Exception:
                pass
        else:
            warnings.append("pip is not available in PATH")

        # Check key packages
        key_packages = {
            "requests": "requests",
            "psutil": "psutil",
            "yaml": "yaml",
        }
        for pkg_name, import_name in key_packages.items():
            try:
                __import__(import_name)
                details["key_packages"][pkg_name] = "installed"
            except ImportError:
                details["key_packages"][pkg_name] = "missing"
                warnings.append(f"Recommended package '{pkg_name}' is not installed")

        result.details = details
        result.warnings = warnings
        result.recommendations = [
            "Use a virtual environment for dependency isolation",
            "Install recommended packages: pip install requests psutil pyyaml",
        ]
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # PATH Integrity
    # ------------------------------------------------------------------

    def check_path_integrity(self) -> EnvironmentHardeningResult:
        """
        Check PATH environment variable for accessibility and integrity.

        Validates that common required tools are accessible and that
        PATH entries are valid.
        """
        start = datetime.now(timezone.utc)
        result = EnvironmentHardeningResult(check_name="path_integrity")
        path = os.environ.get("PATH", "")
        path_entries = [p.strip() for p in path.split(";") if p.strip()]

        details: Dict[str, Any] = {
            "path_entries_count": len(path_entries),
            "missing_entries": [],
            "accessible_tools": {},
            "path_length": len(path),
        }
        warnings: List[str] = []

        # Check for invalid/missing PATH entries
        for entry in path_entries:
            if not os.path.exists(entry) and not os.path.exists(os.path.join(entry, ".")):
                details["missing_entries"].append(entry)

        if details["missing_entries"]:
            warnings.append(
                f"Found {len(details['missing_entries'])} missing PATH entries"
            )

        # Check essential tools
        essential_tools = [
            "git",
            "curl",
            "python",
            "powershell",
        ]
        for tool in essential_tools:
            tool_path = shutil.which(tool)
            details["accessible_tools"][tool] = tool_path is not None

        all_tools_ok = all(details["accessible_tools"].values())
        if not all_tools_ok:
            missing = [
                t for t, found in details["accessible_tools"].items()
                if not found
            ]
            warnings.append(f"Some essential tools are not in PATH: {', '.join(missing)}")
            result.recommendations = [
                "Ensure Git, curl, and PowerShell are installed and in PATH",
            ]

        result.passed = all_tools_ok
        result.details = details
        result.warnings = warnings
        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return result

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_results(self) -> List[EnvironmentHardeningResult]:
        """Get all hardening check results."""
        return self._results

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all hardening checks."""
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        return {
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "warnings": sum(len(r.warnings) for r in self._results),
            "errors": sum(len(r.errors) for r in self._results),
            "system_info": self._system_info,
            "checks": [r.to_dict() for r in self._results],
        }
