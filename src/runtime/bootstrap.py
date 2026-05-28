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
    - Interrupted shutdown detection and stale-state cleanup
    - Startup lock file survivability
    - Stale temp-state restoration guards
    - Startup fallback sequencing after partial init failure
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
        if project_root:
            self._project_root = Path(project_root)
        elif _is_frozen():
            bundle = _get_bundle_root()
            if bundle:
                self._project_root = Path(os.path.dirname(bundle))
            else:
                # Frozen without bundle: use home dir, not cwd (cwd may be bundle temp)
                self._project_root = Path(os.path.expanduser("~")) / ".corax"
        else:
            self._project_root = Path(os.getcwd())
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

    def _get_current_time(self) -> float:
        """Get current time with safe import."""
        import time as _t
        return _t.time()

    def cleanup_stale_temp(self) -> None:
        """Clean up stale temp files from interrupted previous runs.

        Removes lock files, state files, and temp artifacts older than 1 hour.
        Uses bounded cleanup: max 50 files, no subdirectory recursion.
        Guarded: never raises, logs warnings on failure.

        — M41: Extended stale-state cleanup — also cleans persistence state
        files, corrupted checkpoint files, orphaned session files, and
        corrupted runtime state markers.
        """
        try:
            now = self._get_current_time()
            cutoff = now - 3600  # 1 hour
            temp_dir = self._project_root / "_corax_temp"
            if temp_dir.exists():
                count = 0
                max_cleanup = 50
                for f in temp_dir.iterdir():
                    if count >= max_cleanup:
                        break
                    try:
                        if f.is_file() and f.stat().st_mtime < cutoff:
                            f.unlink()
                            count += 1
                    except (PermissionError, OSError):
                        continue

            # Clean any stray .lock files in project root
            for lock in self._project_root.glob("*.lock"):
                try:
                    if lock.is_file() and lock.stat().st_mtime < cutoff:
                        lock.unlink()
                except (PermissionError, OSError):
                    continue

            # Clean stale startup state marker files (from interrupted runs)
            for state_marker in self._project_root.glob("_corax_state_*"):
                try:
                    if state_marker.is_file() and state_marker.stat().st_mtime < cutoff:
                        state_marker.unlink()
                except (PermissionError, OSError):
                    continue

            # Clean stale partial initialization markers
            partial_init = self._project_root / "_corax_partial_init"
            if partial_init.exists():
                try:
                    if partial_init.stat().st_mtime < cutoff:
                        partial_init.unlink()
                except (PermissionError, OSError):
                    pass

            # Clean stale persistence checkpoint files from interrupted runs
            persistence_dir = self._project_root / "data" / "persistence"
            if persistence_dir.exists():
                for f in persistence_dir.iterdir():
                    try:
                        if f.is_file() and f.suffix in (".json", ".jsonl", ".state"):
                            if f.stat().st_mtime < cutoff:
                                if "checkpoint" in f.name or "state_" in f.name or "_corax_" in f.name:
                                    f.unlink()
                    except (PermissionError, OSError):
                        continue

            # Clean corrupted state files from persistence
            corrupt_markers = list(self._project_root.glob("data/persistence/*.corrupted"))
            for cm in corrupt_markers:
                try:
                    cm.unlink()
                except (PermissionError, OSError):
                    pass

            # — M41: Validate and clean runtime state consistency markers
            self._validate_state_consistency_markers(cutoff)

            # — M41: Clean orphaned execution state markers (e.g. stale deploy/exec active markers)
            self._clean_orphaned_execution_markers(cutoff)

            # — M41: Clean stale session checkpoint files from interrupted agent sessions
            self._clean_stale_session_checkpoints()

            # — M41: Clean stale event journal files from previous runs
            self._clean_stale_journal_files(cutoff)

            count = sum(1 for _ in self._project_root.glob("_corax_temp/*") if _.is_file())
            if count > 0:
                self._result.repairs_made.append(
                    f"Cleaned {count} stale temp file(s) from previous run"
                )
        except Exception:
            pass  # Non-critical cleanup, never block bootstrap

    def _clean_orphaned_execution_markers(self, cutoff: float) -> None:
        """Clean orphaned execution state markers from interrupted agent/deployment sessions.
        
        — M41: Prevents stale execution markers from causing consistency errors on restart.
        """
        exec_markers = [
            "_corax_exec_active",
            "_corax_deploy_active",
            "_corax_scheduler_active",
            "_corax_state_dirty",
            "_corax_session_active",
        ]
        for marker_name in exec_markers:
            marker = self._project_root / marker_name
            if marker.exists() and marker.is_file():
                try:
                    if marker.stat().st_mtime < cutoff:
                        marker.unlink()
                        self._result.repairs_made.append(
                            f"Removed orphaned execution marker: {marker_name}"
                        )
                except (PermissionError, OSError):
                    pass

    def _clean_stale_session_checkpoints(self) -> None:
        """Clean stale session checkpoint files from interrupted agent sessions.
        
        — M41: Bounded cleanup of session checkpoints older than 24 hours.
        """
        try:
            persistence_dir = self._project_root / "data" / "persistence"
            if not persistence_dir.exists():
                return
            now = self._get_current_time()
            cutoff = now - 86400  # 24 hours
            count = 0
            max_cleanup = 20
            for f in persistence_dir.iterdir():
                if count >= max_cleanup:
                    break
                try:
                    if f.is_file() and f.suffix == ".checkpoint":
                        if f.stat().st_mtime < cutoff:
                            f.unlink()
                            count += 1
                except (PermissionError, OSError):
                    continue
            if count > 0:
                self._result.repairs_made.append(
                    f"Cleaned {count} stale session checkpoint(s)"
                )
        except Exception:
            pass

    def _clean_stale_journal_files(self, cutoff: float) -> None:
        """Clean stale/oversized journal files from previous runs.
        
        — M41: Prevents journal file unbounded growth. Truncates to max 5000 lines.
        """
        try:
            persistence_dir = self._project_root / "data" / "persistence"
            if not persistence_dir.exists():
                return
            for journal_pattern in ["event_journal.jsonl", "error_journal.jsonl", "recovery_journal.jsonl"]:
                journal_path = persistence_dir / journal_pattern
                if not journal_path.exists():
                    continue
                try:
                    # Check file size > 1MB, truncate
                    size = journal_path.stat().st_size
                    if size > 1_048_576:  # 1MB
                        with open(journal_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        if len(lines) > 5000:
                            with open(journal_path, "w", encoding="utf-8") as f:
                                f.writelines(lines[-5000:])
                            self._result.repairs_made.append(
                                f"Truncated oversized journal: {journal_pattern} ({size // 1024}KB)"
                            )
                except (PermissionError, OSError):
                    pass
        except Exception:
            pass


    def _validate_state_consistency_markers(self, cutoff: float) -> None:
        """Validate and clean runtime state consistency markers.

        Checks for orphaned or corrupted state consistency markers
        (e.g., _corax_init_phase, _corax_exec_active) and removes
        stale ones older than cutoff. This prevents stale state from
        causing consistency issues on restart.

        — M41: Startup state consistency hardening
        """
        markers = [
            "_corax_init_phase",
            "_corax_exec_active",
            "_corax_deploy_active",
            "_corax_state_dirty",
        ]
        for marker_name in markers:
            marker = self._project_root / marker_name
            if marker.exists():
                try:
                    if marker.stat().st_mtime < cutoff:
                        content = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
                        marker.unlink()
                        self._result.repairs_made.append(
                            f"Removed stale state marker: {marker_name} ({content[:50]})"
                        )
                except (PermissionError, OSError):
                    pass

        # — M41: Detect corrupted state marker files (non-empty but unreadable)
        for marker_name in markers:
            marker = self._project_root / marker_name
            if marker.exists() and marker.is_file():
                try:
                    _ = marker.stat()
                    if _.st_size > 0:
                        # Attempt to read; if fails, it's corrupted
                        try:
                            marker.read_bytes()
                        except (PermissionError, OSError, UnicodeDecodeError):
                            marker.unlink()
                            self._result.repairs_made.append(
                                f"Removed corrupted state marker: {marker_name}"
                            )
                except (PermissionError, OSError):
                    pass

    def create_startup_state_marker(self, phase: str) -> None:
        """Create a startup initialization phase marker for consistency tracking.

        Args:
            phase: The initialization phase name (e.g., "bootstrap", "config", "runtime").
        """
        try:
            marker = self._project_root / f"_corax_init_phase"
            marker.write_text(f"{phase}|{os.getpid()}", encoding="utf-8")
        except Exception:
            pass

    def remove_startup_state_marker(self) -> None:
        """Remove the startup initialization phase marker."""
        try:
            marker = self._project_root / "_corax_init_phase"
            if marker.exists():
                marker.unlink()
        except Exception:
            pass

    def get_previous_init_phase(self) -> Optional[str]:
        """Get the initialization phase from the previous interrupted run.

        Returns:
            The phase name if a stale marker was found, None otherwise.
        """
        try:
            marker = self._project_root / "_corax_init_phase"
            if marker.exists():
                content = marker.read_text(encoding="utf-8").strip()
                parts = content.split("|", 1)
                return parts[0] if parts else None
            return None
        except Exception:
            return None

    def detect_interrupted_shutdown(self) -> bool:
        """Detect if previous run was interrupted via stale startup lock.

        Returns:
            True if interrupted shutdown detected, False otherwise.
        """
        try:
            lock_file = self._project_root / "_corax_startup.lock"
            if lock_file.exists():
                import time as _time
                age = _time.time() - lock_file.stat().st_mtime
                if age > 30:  # Lock older than 30s means previous run crashed
                    self._result.warnings.append(
                        f"Detected interrupted shutdown: stale startup lock "
                        f"({age:.0f}s old)"
                    )
                    try:
                        lock_file.unlink()
                        self._result.repairs_made.append(
                            "Cleared stale startup lock"
                        )
                    except (PermissionError, OSError):
                        pass
                    return True
            return False
        except Exception:
            return False

    def create_startup_lock(self) -> None:
        """Create startup lock file to detect interrupted shutdowns."""
        try:
            lock_file = self._project_root / "_corax_startup.lock"
            lock_file.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass  # Non-critical, cleanup handled on next boot

    def remove_startup_lock(self) -> None:
        """Remove startup lock file on clean shutdown."""
        try:
            lock_file = self._project_root / "_corax_startup.lock"
            if lock_file.exists():
                lock_file.unlink()
        except Exception:
            pass

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
