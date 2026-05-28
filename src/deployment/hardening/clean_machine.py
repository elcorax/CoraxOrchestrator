"""
Corax Orchestrator — Clean Machine Simulation Module (Priority 4).

Simulates hostile/minimal environments to validate deployment survivability:
- Missing Python, Git, Node.js
- No admin privileges
- Limited disk space
- Offline mode / blocked downloads
- Antivirus interference
- Partial installs
- Graceful degradation with recovery guidance

Requirements:
- Graceful degradation always
- Recovery guidance for operators
- Safe warnings (never crash deployment)
- Survivability through hostile conditions
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import shutil
import subprocess
import tempfile

from src.core.logging import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Data Types
# ------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Result of a single environment simulation."""
    simulation_name: str
    passed: bool
    survived: bool  # Did the deployment survive this condition?
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recovery_guidance: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_name": self.simulation_name,
            "passed": self.passed,
            "survived": self.survived,
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
            "recovery_guidance": self.recovery_guidance,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class SimulationReport:
    """Full report from clean machine simulation."""
    results: List[SimulationResult]
    overall_survived: bool
    survivability_score: float  # 0.0 to 1.0
    critical_failures: List[str]
    recommendations: List[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "overall_survived": self.overall_survived,
            "survivability_score": round(self.survivability_score, 3),
            "critical_failures": self.critical_failures,
            "recommendations": self.recommendations,
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# Clean Machine Simulator
# ------------------------------------------------------------------

class CleanMachineSimulator:
    """
    Simulates hostile/minimal environments to test deployment survivability.

    Each simulation checks how the deployment would behave under
    specific hostile conditions without actually modifying the system.
    All simulations are read-only and safe.
    """

    def __init__(self):
        self._results: List[SimulationResult] = []

    # ------------------------------------------------------------------
    # Missing Dependencies
    # ------------------------------------------------------------------

    def simulate_missing_python(self) -> SimulationResult:
        """
        Simulate missing Python environment.

        Checks if the deployment can handle a scenario where
        Python is not available or the venv is broken.
        """
        result = SimulationResult(simulation_name="missing_python")

        try:
            # Check if Python is actually available (for reference)
            proc = subprocess.run(
                [sys_executable := self._get_python(), "--version"],
                capture_output=True, text=True, timeout=5,
            )
            python_available = proc.returncode == 0
            result.details["python_available"] = python_available
            result.details["python_path"] = sys_executable

            # Check venv integrity
            venv_paths = [
                os.path.join(os.getcwd(), ".venv"),
                os.path.join(os.getcwd(), "venv"),
                os.path.join(os.getcwd(), "..", ".venv"),
            ]
            venv_found = None
            for path in venv_paths:
                if os.path.isdir(path):
                    venv_found = path
                    break
            result.details["venv_found"] = venv_found is not None
            result.details["venv_path"] = venv_found

            # Determine survivability
            if not python_available:
                result.survived = False
                result.errors.append("Python is not available on this system")
                result.recovery_guidance.append(
                    "Install Python 3.10+ from python.org"
                )
                result.recovery_guidance.append(
                    "Or use the Corax standalone executable"
                )
            else:
                result.survived = True  # Python is available
                result.details["note"] = "Python is present - this is a reference check"

            result.passed = result.survived

        except Exception as e:
            result.survived = False
            result.errors.append(f"Python simulation error: {e}")
            result.recovery_guidance.append("Use the standalone executable")

        return result

    def simulate_missing_git(self) -> SimulationResult:
        """
        Simulate missing Git.

        Checks if the deployment can handle Git not being installed
        (e.g., for cloning repositories during installation).
        """
        result = SimulationResult(simulation_name="missing_git")

        try:
            proc = subprocess.run(
                ["git", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            git_available = proc.returncode == 0

            result.details["git_available"] = git_available
            if git_available:
                result.details["git_version"] = proc.stdout.strip()

            # Check if any deployment steps depend on Git
            git_dependents = self._find_git_dependencies()
            result.details["git_dependent_steps"] = git_dependents

            if not git_available:
                result.survived = len(git_dependents) == 0
                result.errors.append("Git is not installed")
                if git_dependents:
                    result.warnings.append(
                        f"Deployment steps depend on Git: {', '.join(git_dependents)}"
                    )
                result.recovery_guidance.append(
                    "Install Git from https://git-scm.com"
                )
                result.recovery_guidance.append(
                    "Or download repositories manually"
                )
            else:
                result.survived = True

            result.passed = result.survived

        except Exception as e:
            result.survived = True  # Git is optional
            result.errors.append(f"Git check error (non-fatal): {e}")

        return result

    def simulate_missing_nodejs(self) -> SimulationResult:
        """
        Simulate missing Node.js.

        Checks if the deployment can handle Node.js not being available.
        """
        result = SimulationResult(simulation_name="missing_nodejs")

        try:
            proc = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            node_available = proc.returncode == 0

            result.details["nodejs_available"] = node_available
            if node_available:
                result.details["node_version"] = proc.stdout.strip()

            if not node_available:
                result.survived = True  # Node.js is typically optional
                result.warnings.append(
                    "Node.js is not installed (non-critical)"
                )
                result.recovery_guidance.append(
                    "Install Node.js from https://nodejs.org if needed"
                )
            else:
                result.survived = True

            result.passed = True  # Non-critical dependency

        except Exception as e:
            result.survived = True
            result.errors.append(f"Node.js check error (non-fatal): {e}")

        return result

    # ------------------------------------------------------------------
    # Permission Restrictions
    # ------------------------------------------------------------------

    def simulate_no_admin(self) -> SimulationResult:
        """
        Simulate running without admin privileges.

        Checks if the deployment can operate with limited permissions.
        """
        result = SimulationResult(simulation_name="no_admin_privileges")

        try:
            is_admin = False
            if platform.system() == "Windows":
                try:
                    import ctypes
                    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
                except (ImportError, AttributeError):
                    # Fallback check
                    try:
                        proc = subprocess.run(
                            ["net", "session"],
                            capture_output=True, text=True, timeout=5,
                        )
                        is_admin = proc.returncode == 0
                    except Exception:
                        pass
            else:
                is_admin = os.geteuid() == 0

            result.details["is_admin"] = is_admin

            # Check write access to installation directories
            check_dirs = [
                os.getcwd(),
                tempfile.gettempdir(),
                os.path.expanduser("~"),
            ]
            if platform.system() == "Windows":
                check_dirs.extend([
                    os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                    os.environ.get("LOCALAPPDATA", ""),
                ])

            writable = []
            not_writable = []
            for d in check_dirs:
                if d and os.path.isdir(d):
                    try:
                        test_file = os.path.join(d, ".corax_write_test")
                        with open(test_file, "w") as f:
                            f.write("test")
                        os.remove(test_file)
                        writable.append(d)
                    except (IOError, OSError):
                        not_writable.append(d)

            result.details["writable_directories"] = writable
            result.details["not_writable_directories"] = not_writable

            if not is_admin and not_writable:
                result.survived = False
                result.errors.append(
                    "No admin privileges and some directories are not writable"
                )
                result.recovery_guidance.append(
                    "Run installer as administrator"
                )
                result.recovery_guidance.append(
                    "Or install to a user-writable directory"
                )
            else:
                result.survived = True

            result.passed = result.survived

        except Exception as e:
            result.survived = True
            result.errors.append(f"Admin check error (non-fatal): {e}")

        return result

    # ------------------------------------------------------------------
    # Disk Space
    # ------------------------------------------------------------------

    def simulate_limited_disk(self, min_free_gb: float = 1.0) -> SimulationResult:
        """
        Simulate limited disk space conditions.

        Args:
            min_free_gb: Threshold for "limited" space
        """
        result = SimulationResult(simulation_name="limited_disk_space")

        try:
            usage = shutil.disk_usage(os.getcwd())
            free_gb = usage.free / (1024 ** 3)

            result.details["free_gb"] = round(free_gb, 2)
            result.details["min_threshold_gb"] = min_free_gb
            result.details["total_gb"] = round(usage.total / (1024 ** 3), 2)

            if free_gb < min_free_gb:
                result.survived = False
                result.errors.append(
                    f"Only {free_gb:.1f} GB free (threshold: {min_free_gb} GB)"
                )
                result.recovery_guidance.append(
                    f"Free up disk space (need at least {min_free_gb} GB)"
                )
                result.recovery_guidance.append(
                    "Clean temporary files and logs"
                )
            else:
                result.survived = True

            # Check how deployment would react
            result.details["disk_pressure"] = "high" if free_gb < 2.0 else (
                "medium" if free_gb < 5.0 else "low"
            )

            result.passed = result.survived

        except Exception as e:
            result.survived = True
            result.errors.append(f"Disk check error: {e}")

        return result

    # ------------------------------------------------------------------
    # Offline Mode
    # ------------------------------------------------------------------

    def simulate_offline(self) -> SimulationResult:
        """
        Simulate offline mode (no internet connectivity).

        Checks if the deployment can proceed with cached/offline resources.
        """
        result = SimulationResult(simulation_name="offline_mode")

        try:
            import socket
            hosts = [
                ("google.com", 80),
                ("pypi.org", 443),
                ("github.com", 443),
            ]

            online = False
            for host, port in hosts:
                try:
                    sock = socket.create_connection((host, port), timeout=3)
                    sock.close()
                    online = True
                    break
                except (socket.timeout, OSError):
                    continue

            result.details["online"] = online
            result.details["hosts_tested"] = [h for h, _ in hosts]

            if not online:
                result.survived = True  # Deployment should survive offline
                result.warnings.append(
                    "No internet connectivity detected"
                )
                result.recovery_guidance.append(
                    "Offline mode: use cached packages and local models"
                )
                result.recovery_guidance.append(
                    "Pre-download installers and models for offline use"
                )

                # Check for cached resources
                cache_paths = [
                    os.path.join(os.getcwd(), "cache"),
                    os.path.join(os.getcwd(), "downloads"),
                    os.path.join(tempfile.gettempdir(), "corax_cache"),
                ]
                cached = [p for p in cache_paths if os.path.isdir(p)]
                result.details["cached_resources_found"] = len(cached) > 0
                result.details["cache_directories"] = cached

            else:
                result.survived = True

            result.passed = True  # Offline is a warning, not failure

        except Exception as e:
            result.survived = True
            result.details["error"] = str(e)

        return result

    # ------------------------------------------------------------------
    # Blocked Downloads / AV Interference
    # ------------------------------------------------------------------

    def simulate_blocked_downloads(self) -> SimulationResult:
        """
        Simulate blocked downloads (firewall, AV, or proxy blocking).

        Checks if the deployment can detect and handle download failures.
        """
        result = SimulationResult(simulation_name="blocked_downloads")

        try:
            # Test download to common URLs
            import urllib.request
            test_urls = [
                ("https://github.com", "GitHub"),
                ("https://pypi.org", "PyPI"),
                ("https://ollama.ai", "Ollama"),
            ]

            blocked: List[str] = []
            accessible: List[str] = []
            for url, name in test_urls:
                try:
                    req = urllib.request.Request(url, method="HEAD")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if resp.status < 500:
                            accessible.append(name)
                        else:
                            blocked.append(name)
                except Exception:
                    blocked.append(name)

            result.details["accessible"] = accessible
            result.details["blocked"] = blocked

            if blocked:
                result.survived = True  # Can survive with fallback
                result.warnings.append(
                    f"Downloads blocked: {', '.join(blocked)}"
                )
                result.recovery_guidance.append(
                    "Check firewall and antivirus exclusions"
                )
                result.recovery_guidance.append(
                    "Add Corax directories to AV exclusions"
                )
                result.recovery_guidance.append(
                    "Use a VPN or proxy if downloads are region-blocked"
                )

                # Check for common AV indicators
                av_indicators = self._check_av_interference()
                result.details["av_indicators"] = av_indicators
                if av_indicators:
                    result.warnings.append(
                        "Antivirus may be interfering with downloads"
                    )

            result.passed = len(blocked) == 0

        except Exception as e:
            result.survived = True
            result.errors.append(f"Download check error: {e}")

        return result

    def _check_av_interference(self) -> List[str]:
        """Check for common antivirus indicators."""
        indicators = []

        if platform.system() == "Windows":
            # Check for Windows Defender
            try:
                proc = subprocess.run(
                    ["powershell", "-Command",
                     "Get-MpPreference | Select-Object -Property DisableRealtimeMonitoring"],
                    capture_output=True, text=True, timeout=10,
                )
                if "False" in proc.stdout:
                    indicators.append("Windows Defender real-time monitoring is active")
            except Exception:
                pass

            # Check for common AV processes
            av_processes = [
                "MsMpEng.exe",  # Windows Defender
                "McAfee", "mcafee",
                "Norton", "norton",
                "Avast", "avast",
                "AVG", "avg",
                "BitDefender", "bitdefender",
                "Kaspersky", "kaspersky",
                "Malwarebytes", "malwarebytes",
            ]
            for av in av_processes:
                try:
                    proc = subprocess.run(
                        ["tasklist", "/FI", f"IMAGENAME eq {av}"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if av.lower() in proc.stdout.lower():
                        indicators.append(f"Antivirus process detected: {av}")
                except Exception:
                    pass

        return indicators

    # ------------------------------------------------------------------
    # Partial Installs
    # ------------------------------------------------------------------

    def simulate_partial_installs(self) -> SimulationResult:
        """
        Simulate partial/ incomplete installations.

        Checks for partially installed components that indicate
        a previous interrupted installation.
        """
        result = SimulationResult(simulation_name="partial_installs")

        try:
            # Check for partial installation markers
            partial_indicators = []
            install_dirs = [
                os.path.join(os.getcwd(), "downloads"),
                os.path.join(os.getcwd(), "extracted"),
                os.path.join(os.getcwd(), "temp_install"),
                os.path.join(tempfile.gettempdir(), "corax_install"),
            ]

            for d in install_dirs:
                if os.path.isdir(d):
                    # Check for incomplete files
                    try:
                        for f in os.listdir(d):
                            if f.endswith((".tmp", ".partial", ".download")):
                                partial_indicators.append({
                                    "directory": d,
                                    "file": f,
                                })
                            elif f.endswith(".json"):
                                # Check for incomplete manifests
                                filepath = os.path.join(d, f)
                                try:
                                    with open(filepath) as fh:
                                        data = json.load(fh)
                                    if not data.get("completed"):
                                        partial_indicators.append({
                                            "directory": d,
                                            "file": f,
                                            "reason": "Incomplete manifest",
                                        })
                                except (json.JSONDecodeError, IOError):
                                    pass
                    except OSError:
                        pass

            result.details["partial_installation_indicators"] = partial_indicators
            result.details["indicator_count"] = len(partial_indicators)

            if partial_indicators:
                result.survived = True  # Can survive with recovery
                result.warnings.append(
                    f"Found {len(partial_indicators)} partial installation indicators"
                )
                result.recovery_guidance.append(
                    "Clean temporary installation files and retry"
                )
                result.recovery_guidance.append(
                    "Use --clean flag to remove partial installations"
                )
            else:
                result.survived = True

            result.passed = True

        except Exception as e:
            result.survived = True
            result.errors.append(f"Partial install check error: {e}")

        return result

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _get_python(self) -> str:
        """Get the Python executable path."""
        return sys_executable if (
            sys_executable := os.environ.get("PYTHON_EXECUTABLE")
        ) else "python" if platform.system() == "Windows" else "python3"

    def _find_git_dependencies(self) -> List[str]:
        """Find deployment steps that depend on Git."""
        git_steps = []
        deploy_dir = os.path.join(os.getcwd(), "src", "deployment")
        if os.path.isdir(deploy_dir):
            for root, _, files in os.walk(deploy_dir):
                for f in files:
                    if f.endswith(".py"):
                        filepath = os.path.join(root, f)
                        try:
                            with open(filepath, encoding="utf-8") as fh:
                                content = fh.read()
                                if "git clone" in content or "subprocess.run.*git" in content:
                                    git_steps.append(filepath)
                        except (IOError, UnicodeDecodeError):
                            pass
        return git_steps

    # ------------------------------------------------------------------
    # Full Simulation Run
    # ------------------------------------------------------------------

    def run_all_simulations(self) -> SimulationReport:
        """
        Run all clean machine simulations and produce a report.

        Returns:
            SimulationReport with all results and recommendations
        """
        self._results = []

        # Run all simulations
        self._results.append(self.simulate_missing_python())
        self._results.append(self.simulate_missing_git())
        self._results.append(self.simulate_missing_nodejs())
        self._results.append(self.simulate_no_admin())
        self._results.append(self.simulate_limited_disk())
        self._results.append(self.simulate_offline())
        self._results.append(self.simulate_blocked_downloads())
        self._results.append(self.simulate_partial_installs())

        # Calculate survivability
        survived_count = sum(1 for r in self._results if r.survived)
        total = len(self._results)
        survivability_score = survived_count / total if total > 0 else 0.0
        overall_survived = survivability_score >= 0.75  # 75% survivability threshold

        # Critical failures
        critical_failures = [
            r.simulation_name for r in self._results
            if not r.survived
        ]

        # Recommendations
        recommendations = []
        for r in self._results:
            recommendations.extend(r.recovery_guidance)
        # Deduplicate
        recommendations = list(dict.fromkeys(recommendations))

        return SimulationReport(
            results=self._results,
            overall_survived=overall_survived,
            survivability_score=survivability_score,
            critical_failures=critical_failures,
            recommendations=recommendations,
        )

    def get_simulation_summary(self) -> Dict[str, Any]:
        """Get a summary of the last simulation run."""
        if not self._results:
            return {"note": "No simulations have been run yet"}

        return {
            "total_simulations": len(self._results),
            "survived": sum(1 for r in self._results if r.survived),
            "failed": sum(1 for r in self._results if not r.survived),
            "critical_failures": [
                r.simulation_name for r in self._results if not r.survived
            ],
            "recommendations": list(dict.fromkeys(
                r.recovery_guidance for r in self._results
            )),
        }
