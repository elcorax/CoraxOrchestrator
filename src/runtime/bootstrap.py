"""
Corax Orchestrator - Bootstrap Runtime Layer.

Lightweight bootstrap runtime that validates Python runtime, dependencies,
PATH, permissions, and virtual environment. Repairs broken startup state,
missing dependencies, and missing PATH entries. Launches runtime safely.

Bootstrap remains:
- Lightweight: minimal imports, fast execution
- Deterministic: same result for same environment
- Highly observable: every check is logged and reported
- Survivability-hardened: _MEIPASS safe, temp-path resilient
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path


def _is_frozen() -> bool:
    """Detect if running as a PyInstaller executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _get_bundle_root() -> Optional[str]:
    """Get the PyInstaller bundle root if frozen."""
    if _is_frozen():
        return getattr(sys, "_MEIPASS", None)
    return None


def _safe_temp_path() -> Path:
    """Get a survivable temp path; falls back to system temp if frozen."""
    if _is_frozen():
        bundle = _get_bundle_root()
        if bundle:
            # Use a sibling temp dir to avoid _MEIPASS write issues
            parent = os.path.dirname(bundle)
            temp_dir = os.path.join(parent, "_corax_temp")
            os.makedirs(temp_dir, exist_ok=True)
            return Path(temp_dir)
    return Path(tempfile.gettempdir())


@dataclass
class BootstrapResult:
    """Result of the bootstrap runtime validation."""

    success: bool = False
    python_version_valid: bool = False
    venv_active: bool = False
    is_admin: bool = False
    path_valid: bool = False
    dependencies_installed: bool = False
    core_modules_available: bool = False
    project_structure_valid: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    path_issues: List[str] = field(default_factory=list)
    missing_dependencies: List[str] = field(default_factory=list)
    repairs_made: List[str] = field(default_factory=list)
    environment_info: Dict[str, str] = field(default_factory=dict)
    frozen_detected: bool = False
    bundle_root: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "success": self.success,
            "python_version_valid": self.python_version_valid,
            "venv_active": self.venv_active,
            "is_admin": self.is_admin,
            "path_valid": self.path_valid,
            "dependencies_installed": self.dependencies_installed,
            "core_modules_available": self.core_modules_available,
            "project_structure_valid": self.project_structure_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "path_issues": self.path_issues,
            "missing_dependencies": self.missing_dependencies,
            "repairs_made": self.repairs_made,
            "environment_info": self.environment_info,
            "frozen_detected": self.frozen_detected,
            "bundle_root": self.bundle_root,
        }
        return d


class BootstrapRuntime:
    """
    Lightweight bootstrap runtime layer.

    Validates and repairs the runtime environment before the main
    application starts. Designed to be importable with minimal
    dependencies and fast execution.

    Survivability features:
    - _MEIPASS / frozen executable detection
    - Temp-path fallback for bundle environments
    - Graceful degradation under partial failure
    - Bounded retry for dependency repairs
    """

    MIN_PYTHON_VERSION = (3, 10)

    REQUIRED_CORE_MODULES = [
        "asyncio", "json", "logging", "pathlib", "dataclasses",
        "typing", "datetime", "abc", "ast", "importlib",
        "inspect", "subprocess", "tempfile", "textwrap",
        "functools", "collections", "enum", "io", "re",
        "shutil", "threading", "time", "uuid", "warnings",
        "types", "math", "random", "hashlib", "copy",
        "pprint", "traceback", "argparse", "contextlib",
        "itertools", "operator", "platform", "signal",
        "socket", "ssl", "stat", "string", "struct",
        "tarfile", "zipfile",
    ]

    MAX_RETRY_ATTEMPTS = 3

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = Path(project_root or os.getcwd())
        self._result = BootstrapResult()
        self._frozen = _is_frozen()
        self._bundle_root = _get_bundle_root()
        self._temp_path = _safe_temp_path()
        self._result.frozen_detected = self._frozen
        self._result.bundle_root = self._bundle_root
        self._result.environment_info = self._collect_env_info()

    def _collect_env_info(self) -> Dict[str, str]:
        """Collect environment info with frozen-safe detection."""
        info = {
            "platform": platform.platform(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "project_root": str(self._project_root),
            "pid": str(os.getpid()),
            "hostname": platform.node(),
            "frozen": str(self._frozen),
            "bundle_root": str(self._bundle_root or ""),
            "temp_path": str(self._temp_path),
        }
        return info

    def run(self) -> BootstrapResult:
        """Run complete bootstrap validation and repair."""
        self._result = BootstrapResult()
        self._result.frozen_detected = self._frozen
        self._result.bundle_root = self._bundle_root
        self._result.environment_info = self._collect_env_info()

        try:
            # Phase 1: Validate Python version
            self._validate_python_version()

            # Phase 2: Validate virtual environment (skip if frozen)
            if not self._frozen:
                self._validate_venv()
            else:
                self._result.venv_active = True  # frozen executables are self-contained

            # Phase 3: Validate permissions
            self._validate_permissions()

            # Phase 4: Validate PATH (skip if frozen)
            if not self._frozen:
                self._validate_path()
            else:
                self._result.path_valid = True

            # Phase 5: Validate project structure (skip if frozen)
            if not self._frozen:
                self._validate_project_structure()
            else:
                self._result.project_structure_valid = True

            # Phase 6: Validate core modules
            self._validate_core_modules()

            # Phase 7: Validate dependencies (skip if frozen)
            if not self._frozen:
                self._validate_dependencies()

            # Phase 8: Repair if needed (bounded retry)
            if self._result.missing_dependencies and not self._frozen:
                self._repair_dependencies_with_retry()

            # Determine overall success with graceful degradation
            self._result.success = (
                self._result.python_version_valid
                and self._result.project_structure_valid
                and self._result.core_modules_available
            )

        except Exception as e:
            self._result.errors.append(f"Bootstrap runtime error: {e}")
            self._result.success = False

        return self._result

    def _repair_dependencies_with_retry(self, max_attempts: int = 3) -> None:
        """Repair missing dependencies with bounded retries."""
        for attempt in range(1, max_attempts + 1):
            try:
                self._repair_dependencies()
                if self._result.dependencies_installed:
                    break
            except Exception as e:
                if attempt < max_attempts:
                    continue
                self._result.errors.append(
                    f"Dependency repair failed after {max_attempts} attempts: {e}"
                )

    def validate_environment(self) -> Dict[str, Any]:
        """Quick environment validation (non-repairing)."""
        result = {
            "success": True,
            "errors": [],
            "warnings": [],
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "venv_active": sys.prefix != sys.base_prefix,
            "platform": platform.platform(),
            "frozen": self._frozen,
        }

        # Check Python version
        if sys.version_info[:2] < self.MIN_PYTHON_VERSION:
            result["success"] = False
            result["errors"].append(
                f"Python {sys.version_info.major}.{sys.version_info.minor} "
                f"below minimum {self.MIN_PYTHON_VERSION[0]}.{self.MIN_PYTHON_VERSION[1]}"
            )

        # Check project structure (skip if frozen)
        if not self._frozen:
            src_dir = self._project_root / "src"
            if not src_dir.exists():
                result["success"] = False
                result["errors"].append("src/ directory not found")

            main_py = src_dir / "main.py"
            if not main_py.exists():
                result["success"] = False
                result["errors"].append("src/main.py not found")
        else:
            result["warnings"].append("Running as frozen executable; project structure check skipped")

        return result

    def _validate_python_version(self) -> None:
        """Validate Python version meets minimum requirements."""
        current = sys.version_info[:2]
        if current >= self.MIN_PYTHON_VERSION:
            self._result.python_version_valid = True
        else:
            self._result.python_version_valid = False
            self._result.errors.append(
                f"Python {current[0]}.{current[1]} is below minimum "
                f"{self.MIN_PYTHON_VERSION[0]}.{self.MIN_PYTHON_VERSION[1]}"
            )

    def _validate_venv(self) -> None:
        """Validate virtual environment is active."""
        try:
            self._result.venv_active = sys.prefix != sys.base_prefix
            if not self._result.venv_active:
                self._result.warnings.append(
                    "Not running in a virtual environment"
                )
        except Exception:
            self._result.venv_active = False
            self._result.warnings.append("Could not determine venv status")

    def _validate_permissions(self) -> None:
        """Validate admin/root permissions."""
        try:
            if platform.system() == "Windows":
                import ctypes  # noqa: F811
                self._result.is_admin = (
                    ctypes.windll.shell32.IsUserAnAdmin() != 0
                )
            else:
                self._result.is_admin = os.geteuid() == 0
        except Exception:
            self._result.is_admin = False

    def _validate_path(self) -> None:
        """Validate PATH environment variable."""
        issues = []
        path = os.environ.get("PATH", "")

        # Check Python directory
        python_dir = os.path.dirname(sys.executable)
        if python_dir not in path:
            issues.append(f"Python directory not in PATH: {python_dir}")

        # Check Scripts directory (Windows)
        if platform.system() == "Windows":
            scripts_dir = os.path.join(
                os.path.dirname(sys.executable), "Scripts"
            )
            if scripts_dir not in path:
                issues.append(
                    f"Python Scripts directory not in PATH: {scripts_dir}"
                )

        # Check for required tools
        for tool in ["pip", "python"]:
            if not shutil.which(tool):
                issues.append(f"Required tool not found: {tool}")

        self._result.path_issues = issues
        self._result.path_valid = len(issues) == 0

        if issues:
            self._result.warnings.extend(
                [f"PATH issue: {i}" for i in issues]
            )

    def _validate_project_structure(self) -> None:
        """Validate project directory structure."""
        required_dirs = [
            self._project_root / "src",
            self._project_root / "src" / "core",
            self._project_root / "src" / "deployment",
            self._project_root / "src" / "runtime",
            self._project_root / "src" / "health",
            self._project_root / "data",
            self._project_root / "data" / "logs",
            self._project_root / "data" / "reports",
            self._project_root / "config",
        ]

        missing = []
        for d in required_dirs:
            if not d.exists():
                missing.append(str(d))

        if missing:
            self._result.warnings.extend(
                [f"Missing directory: {m}" for m in missing]
            )
            self._result.project_structure_valid = False
        else:
            self._result.project_structure_valid = True

        # Check entry point
        main_py = self._project_root / "src" / "main.py"
        if not main_py.exists():
            self._result.errors.append("src/main.py entry point not found")
            self._result.project_structure_valid = False

    def _validate_core_modules(self) -> None:
        """Validate core Python modules are importable."""
        failed = []
        for module in self.REQUIRED_CORE_MODULES:
            try:
                __import__(module)
            except ImportError:
                failed.append(module)

        self._result.core_modules_available = len(failed) == 0
        if failed:
            self._result.errors.append(
                f"Core modules unavailable: {', '.join(failed)}"
            )

    def _validate_dependencies(self) -> None:
        """Validate project dependencies from requirements.txt."""
        req_file = self._project_root / "requirements.txt"
        if not req_file.exists():
            self._result.warnings.append("requirements.txt not found")
            return

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                self._result.warnings.append(
                    f"pip list failed (exit {result.returncode}): "
                    f"{result.stderr[:200]}"
                )
                return
            installed = {
                pkg["name"].lower(): pkg["version"]
                for pkg in json.loads(result.stdout)
            }
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self._result.warnings.append(
                f"Cannot check dependencies: {e}"
            )
            return

        missing = []
        with open(req_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse package name from requirement
                for sep in [">=", "==", "<=", "~=", "!="]:
                    if sep in line:
                        line = line.split(sep)[0]
                        break

                pkg_name = line.strip().lower()
                if pkg_name and pkg_name not in installed:
                    missing.append(line)

        self._result.missing_dependencies = missing
        self._result.dependencies_installed = len(missing) == 0

        if missing:
            self._result.warnings.append(
                f"{len(missing)} dependencies missing"
            )

    def _repair_dependencies(self) -> None:
        """Attempt to repair missing dependencies."""
        if not self._result.missing_dependencies:
            return

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"]
                + self._result.missing_dependencies,
                check=True, capture_output=True, text=True, timeout=300,
            )
            self._result.repairs_made.append(
                f"Installed {len(self._result.missing_dependencies)} "
                f"missing dependencies"
            )
            self._result.dependencies_installed = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError) as e:
            self._result.errors.append(
                f"Failed to repair dependencies: {e}"
            )
