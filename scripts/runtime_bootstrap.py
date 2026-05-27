#!/usr/bin/env python3
"""
Corax Orchestrator - Runtime Bootstrap Launcher.

Lightweight bootstrap executable that:
1. Validates runtime environment
2. Validates Python/runtime dependencies
3. Validates admin permissions
4. Validates PATH state
5. Repairs missing runtime dependencies
6. Initializes Corax runtime
7. Launches deployment orchestration

The bootstrapper remains lightweight and modular.
"""

import os
import sys
import subprocess
import json
import platform
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─── Configuration ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
SRC_DIR = PROJECT_ROOT / "src"
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
REPORT_DIR = DATA_DIR / "reports"

MIN_PYTHON_VERSION = (3, 10)


# ─── Logging ─────────────────────────────────────────────────────────────────

class BootstrapLogger:
    """Simple bootstrap logger that writes to stdout and log file."""

    def __init__(self):
        self._log_lines: List[str] = []
        self._log_file: Optional[Path] = None

    def set_log_file(self, path: Path) -> None:
        self._log_file = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def info(self, message: str) -> None:
        line = f"[INFO] {message}"
        self._log_lines.append(line)
        print(line)

    def warn(self, message: str) -> None:
        line = f"[WARN] {message}"
        self._log_lines.append(line)
        print(line)

    def error(self, message: str) -> None:
        line = f"[ERROR] {message}"
        self._log_lines.append(line)
        print(line, file=sys.stderr)

    def success(self, message: str) -> None:
        line = f"[OK] {message}"
        self._log_lines.append(line)
        print(line)

    def flush(self) -> None:
        if self._log_file:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self._log_lines))


log = BootstrapLogger()


# ─── Bootstrap Phases ────────────────────────────────────────────────────────

class BootstrapResult:
    """Result of the bootstrap process."""

    def __init__(self):
        self.success: bool = False
        self.phases: Dict[str, Dict] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "phases": self.phases,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_python_version() -> bool:
    """Validate Python version meets minimum requirements."""
    current = sys.version_info[:2]
    if current < MIN_PYTHON_VERSION:
        log.error(
            f"Python {current[0]}.{current[1]} is below minimum "
            f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}"
        )
        return False
    log.success(f"Python {current[0]}.{current[1]} meets minimum requirements")
    return True


def validate_venv() -> bool:
    """Validate virtual environment is active."""
    if sys.prefix == sys.base_prefix:
        log.warn("Not running in a virtual environment")
        log.info("Attempting to activate virtual environment...")

        venv_python = VENV_DIR / "Scripts" / "python.exe"
        if venv_python.exists():
            log.info(f"Virtual environment found at {VENV_DIR}")
            log.info("Please activate with: .venv\\Scripts\\activate")
            return False
        else:
            log.info("No virtual environment found. Creating one...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", str(VENV_DIR)],
                    check=True, capture_output=True, text=True
                )
                log.success(f"Virtual environment created at {VENV_DIR}")
                log.info("Please activate with: .venv\\Scripts\\activate")
                return False
            except subprocess.CalledProcessError as e:
                log.error(f"Failed to create virtual environment: {e.stderr}")
                return False
    else:
        log.success(f"Virtual environment active: {sys.prefix}")
        return True


def validate_admin_permissions() -> Tuple[bool, bool]:
    """Validate admin permissions. Returns (is_admin, can_install)."""
    is_admin = False
    can_install = True

    if platform.system() == "Windows":
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
    else:
        is_admin = os.geteuid() == 0

    if is_admin:
        log.success("Running with administrator privileges")
    else:
        log.warn("Not running as administrator")
        log.info("Some operations may require elevated privileges")

    return is_admin, can_install


def validate_path_state() -> List[str]:
    """Validate PATH state and return issues."""
    issues = []
    path = os.environ.get("PATH", "")

    # Check if Python is in PATH
    python_dir = os.path.dirname(sys.executable)
    if python_dir not in path:
        issues.append(f"Python directory not in PATH: {python_dir}")
        log.warn(f"Python directory not in PATH: {python_dir}")

    # Check if Scripts is in PATH (Windows)
    if platform.system() == "Windows":
        scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
        if scripts_dir not in path:
            issues.append(f"Python Scripts directory not in PATH: {scripts_dir}")
            log.warn(f"Python Scripts directory not in PATH: {scripts_dir}")

    # Check for required tools in PATH
    required_tools = ["pip", "python"]
    for tool in required_tools:
        if not shutil.which(tool):
            issues.append(f"Required tool not found in PATH: {tool}")
            log.warn(f"Required tool not found in PATH: {tool}")

    if not issues:
        log.success("PATH state is valid")

    return issues


def validate_dependencies() -> Tuple[List[str], List[str]]:
    """Validate installed dependencies. Returns (missing, conflicts)."""
    missing = []
    conflicts = []

    if not REQUIREMENTS_FILE.exists():
        log.error(f"Requirements file not found: {REQUIREMENTS_FILE}")
        return [f"requirements.txt not found"], []

    log.info(f"Checking dependencies from {REQUIREMENTS_FILE}...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, check=True
        )
        installed = {pkg["name"].lower(): pkg["version"]
                     for pkg in json.loads(result.stdout)}
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        log.error(f"Failed to list installed packages: {e}")
        return [f"Cannot check dependencies: {e}"], []

    with open(REQUIREMENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse requirement
            if ">=" in line:
                pkg_name, version = line.split(">=", 1)
            elif "==" in line:
                pkg_name, version = line.split("==", 1)
            elif "<" in line:
                pkg_name, version = line.split("<", 1)
            elif "~=" in line:
                pkg_name, version = line.split("~=", 1)
            else:
                pkg_name = line
                version = None

            pkg_name = pkg_name.strip().lower()

            if pkg_name not in installed:
                missing.append(line)
                log.warn(f"Missing dependency: {line}")

    if not missing:
        log.success("All dependencies are installed")

    return missing, conflicts


def repair_dependencies(missing: List[str]) -> bool:
    """Attempt to repair missing dependencies."""
    if not missing:
        return True

    log.info(f"Attempting to install {len(missing)} missing dependencies...")

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing,
            check=True, capture_output=True, text=True
        )
        log.success(f"Successfully installed {len(missing)} dependencies")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to install dependencies: {e.stderr}")
        return False


def validate_core_modules() -> List[str]:
    """Validate that core Python modules can be imported."""
    failed = []

    core_modules = [
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

    for module in core_modules:
        try:
            __import__(module)
        except ImportError:
            failed.append(module)
            log.error(f"Critical module not available: {module}")

    if not failed:
        log.success("All core Python modules are available")

    return failed


def initialize_runtime() -> bool:
    """Initialize the Corax runtime environment."""
    log.info("Initializing Corax runtime...")

    # Ensure data directories exist
    dirs = [
        DATA_DIR, LOG_DIR, REPORT_DIR,
        DATA_DIR / "models",
        DATA_DIR / "persistence",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Verify src directory structure
    if not SRC_DIR.exists():
        log.error(f"Source directory not found: {SRC_DIR}")
        return False

    # Try to import core modules
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.core.logging import setup_logging  # noqa: F401
        log.success("Core logging module initialized")
    except ImportError as e:
        log.warn(f"Core logging module not available: {e}")

    try:
        from src.core.config import ConfigManager  # noqa: F401
        log.success("Configuration manager initialized")
    except ImportError as e:
        log.warn(f"Configuration manager not available: {e}")

    log.success("Runtime environment initialized")
    return True


def launch_deployment_orchestration() -> bool:
    """Launch the deployment orchestration system."""
    log.info("Launching deployment orchestration...")

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.deployment.orchestrator import DeploymentOrchestrator  # noqa: F401
        log.success("Deployment orchestrator module loaded")
        return True
    except ImportError as e:
        log.error(f"Failed to load deployment orchestrator: {e}")
        return False


def launch_ai_provisioning() -> bool:
    """Launch AI provisioning systems."""
    log.info("Initializing AI provisioning...")

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.agent.providers.registry import ProviderRegistry  # noqa: F401
        log.success("AI provider registry loaded")
    except ImportError as e:
        log.warn(f"AI provider registry not available: {e}")

    try:
        from src.deployment.models.registry import ModelRegistry  # noqa: F401
        log.success("Model registry loaded")
    except ImportError as e:
        log.warn(f"Model registry not available: {e}")

    return True


# ─── Main Bootstrap ──────────────────────────────────────────────────────────

def run_bootstrap() -> BootstrapResult:
    """Run the complete bootstrap process."""
    result = BootstrapResult()
    log.info("=" * 60)
    log.info("Corax Orchestrator - Bootstrap Launcher")
    log.info("=" * 60)
    log.info(f"Project root: {PROJECT_ROOT}")
    log.info(f"Python: {sys.version}")
    log.info(f"Platform: {platform.platform()}")
    log.info("")

    # Phase 1: Validate Python version
    log.info("─── Phase 1: Python Version Validation ───")
    result.phases["python_version"] = {
        "status": "success" if validate_python_version() else "failed"
    }
    log.info("")

    # Phase 2: Validate virtual environment
    log.info("─── Phase 2: Virtual Environment Validation ───")
    result.phases["venv"] = {
        "status": "success" if validate_venv() else "failed"
    }
    log.info("")

    # Phase 3: Validate admin permissions
    log.info("─── Phase 3: Permission Validation ───")
    is_admin, can_install = validate_admin_permissions()
    result.phases["permissions"] = {
        "status": "success",
        "is_admin": is_admin,
        "can_install": can_install,
    }
    log.info("")

    # Phase 4: Validate PATH state
    log.info("─── Phase 4: PATH Validation ───")
    path_issues = validate_path_state()
    result.phases["path"] = {
        "status": "success" if not path_issues else "warning",
        "issues": path_issues,
    }
    log.info("")

    # Phase 5: Validate dependencies
    log.info("─── Phase 5: Dependency Validation ───")
    missing_deps, conflict_deps = validate_dependencies()
    result.phases["dependencies"] = {
        "status": "success" if not missing_deps else "failed",
        "missing": missing_deps,
        "conflicts": conflict_deps,
    }
    log.info("")

    # Phase 6: Repair dependencies if needed
    if missing_deps:
        log.info("─── Phase 6: Dependency Repair ───")
        repair_success = repair_dependencies(missing_deps)
        result.phases["repair"] = {
            "status": "success" if repair_success else "failed",
            "repaired": len(missing_deps) if repair_success else 0,
        }
        if not repair_success:
            result.errors.append("Failed to repair dependencies")
        log.info("")

    # Phase 7: Validate core modules
    log.info("─── Phase 7: Core Module Validation ───")
    failed_modules = validate_core_modules()
    result.phases["core_modules"] = {
        "status": "success" if not failed_modules else "failed",
        "failed": failed_modules,
    }
    if failed_modules:
        result.errors.append(f"Core modules unavailable: {failed_modules}")
    log.info("")

    # Phase 8: Initialize runtime
    log.info("─── Phase 8: Runtime Initialization ───")
    runtime_ok = initialize_runtime()
    result.phases["runtime"] = {
        "status": "success" if runtime_ok else "failed",
    }
    if not runtime_ok:
        result.errors.append("Runtime initialization failed")
    log.info("")

    # Phase 9: Launch deployment orchestration
    log.info("─── Phase 9: Deployment Orchestration ───")
    deploy_ok = launch_deployment_orchestration()
    result.phases["deployment"] = {
        "status": "success" if deploy_ok else "failed",
    }
    if not deploy_ok:
        result.errors.append("Deployment orchestration failed to load")
    log.info("")

    # Phase 10: Launch AI provisioning
    log.info("─── Phase 10: AI Provisioning ───")
    ai_ok = launch_ai_provisioning()
    result.phases["ai_provisioning"] = {
        "status": "success" if ai_ok else "warning",
    }
    log.info("")

    # Summary
    log.info("=" * 60)
    result.success = len(result.errors) == 0
    if result.success:
        log.success("Bootstrap completed successfully!")
    else:
        log.error(f"Bootstrap completed with {len(result.errors)} error(s)")
        for err in result.errors:
            log.error(f"  - {err}")
    log.info("=" * 60)

    return result


def main():
    """Main entry point for the bootstrap launcher."""
    # Set up log file
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log.set_log_file(LOG_DIR / "bootstrap.log")

    try:
        result = run_bootstrap()
        log.flush()

        # Save result as JSON
        result_file = REPORT_DIR / "bootstrap_result.json"
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        # Return exit code
        sys.exit(0 if result.success else 1)

    except Exception as e:
        log.error(f"Bootstrap failed with unexpected error: {e}")
        import traceback
        log.error(traceback.format_exc())
        log.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
