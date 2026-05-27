"""
Corax Orchestrator - Startup Self-Healing Recovery.

Provides automatic startup recovery handling for broken venv, missing
dependencies, broken PATH, missing runtime packages, interrupted startup,
corrupted startup state, partial initialization, and failed deployment
resume. Ensures safe automatic repair with bounded retries and no
infinite loops.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from src.runtime.state import RuntimePhase


@dataclass
class RecoveryAction:
    """A single recovery action taken during startup repair."""

    phase: str
    action: str
    success: bool
    detail: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "action": self.action,
            "success": self.success,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


@dataclass
class RecoveryResult:
    """Result of the startup recovery process."""

    success: bool = False
    actions: List[RecoveryAction] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "actions": [a.to_dict() for a in self.actions],
            "errors": self.errors,
            "warnings": self.warnings,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


class StartupRecovery:
    """
    Startup self-healing recovery system.

    Handles automatic repair of common startup issues with bounded
    retries, safe recovery actions, and comprehensive reporting.
    """

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = Path(project_root or os.getcwd())
        self._max_retries = 3
        self._retry_count: Dict[str, int] = {}
        self._cooldown_seconds: float = 2.0
        self._last_repair_time: Dict[str, float] = {}

    def repair_all(self) -> RecoveryResult:
        """Attempt to repair all common startup issues with bounded retries."""
        result = RecoveryResult()
        result.max_retries = self._max_retries

        # Repair PATH
        self._repair_path(result)

        # Repair data directories
        self._repair_data_directories(result)

        # Repair dependencies
        self._repair_dependencies(result)

        # Repair Python path
        self._repair_python_path(result)

        result.success = len(result.errors) == 0
        return result

    def repair_with_retry(
        self, repair_type: str, max_retries: Optional[int] = None
    ) -> RecoveryResult:
        """
        Repair with bounded retries and cooldown delays.

        Prevents infinite loops by enforcing:
        - Maximum retry count per repair type
        - Cooldown delay between retries
        - Retry exhaustion detection

        Args:
            repair_type: Type of repair to attempt
            max_retries: Maximum retry attempts (default: self._max_retries)

        Returns:
            RecoveryResult with retry tracking
        """
        max_retries = max_retries or self._max_retries
        result = RecoveryResult()
        result.max_retries = max_retries

        # Check retry exhaustion
        current_retries = self._retry_count.get(repair_type, 0)
        if current_retries >= max_retries:
            result.errors.append(
                f"Retry exhausted for '{repair_type}' "
                f"({current_retries}/{max_retries} attempts)"
            )
            result.success = False
            return result

        # Check cooldown
        last_time = self._last_repair_time.get(repair_type, 0.0)
        import time
        elapsed = time.time() - last_time
        if elapsed < self._cooldown_seconds:
            result.warnings.append(
                f"Cooldown active for '{repair_type}' "
                f"({elapsed:.1f}s < {self._cooldown_seconds}s)"
            )
            result.success = False
            return result

        # Attempt repair
        self._retry_count[repair_type] = current_retries + 1
        self._last_repair_time[repair_type] = time.time()
        result.retry_count = current_retries + 1

        # Run the appropriate repair
        if repair_type == "path":
            self._repair_path(result)
        elif repair_type == "dependencies":
            self._repair_dependencies(result)
        elif repair_type == "data_dirs":
            self._repair_data_directories(result)
        elif repair_type == "python_path":
            self._repair_python_path(result)
        elif repair_type == "config":
            self._repair_config(result)
        elif repair_type == "logging":
            self._repair_logging(result)
        elif repair_type == "state":
            self._repair_state(result)
        else:
            # Generic: run all repairs
            self._repair_path(result)
            self._repair_data_directories(result)
            self._repair_dependencies(result)
            self._repair_python_path(result)

        result.success = len(result.errors) == 0
        return result

    def reset_retry_count(self, repair_type: str) -> None:
        """Reset retry count for a repair type (after successful repair)."""
        self._retry_count.pop(repair_type, None)
        self._last_repair_time.pop(repair_type, None)

    def get_retry_summary(self) -> Dict[str, Any]:
        """Get summary of retry state for all repair types."""
        return {
            "retry_counts": dict(self._retry_count),
            "max_retries": self._max_retries,
            "cooldown_seconds": self._cooldown_seconds,
            "exhausted_repairs": [
                k for k, v in self._retry_count.items()
                if v >= self._max_retries
            ],
        }

    def repair_by_phase(self, phase: RuntimePhase) -> RecoveryResult:
        """Repair issues specific to a startup phase."""
        result = RecoveryResult()

        phase_repair_map = {
            RuntimePhase.BOOTSTRAP: self._repair_bootstrap,
            RuntimePhase.VALIDATE: self._repair_validate,
            RuntimePhase.SELF_REPAIR: self._repair_self_repair,
            RuntimePhase.LOAD_CONFIG: self._repair_config,
            RuntimePhase.INIT_LOGGING: self._repair_logging,
            RuntimePhase.INIT_STATE: self._repair_state,
            RuntimePhase.INIT_EXECUTION: self._repair_execution,
            RuntimePhase.INIT_DEPLOYMENT: self._repair_deployment,
            RuntimePhase.INIT_REPORTING: self._repair_reporting,
        }

        repair_func = phase_repair_map.get(phase)
        if repair_func:
            repair_func(result)
        else:
            # Generic repair for unknown phases
            self._repair_path(result)
            self._repair_data_directories(result)
            self._repair_dependencies(result)

        result.success = len(result.errors) == 0
        return result

    def _repair_bootstrap(self, result: RecoveryResult) -> None:
        """Repair bootstrap phase issues."""
        # Ensure Python is available
        if not shutil.which("python") and not shutil.which("python3"):
            result.warnings.append(
                "Python not found in PATH - may need reinstallation"
            )

        # Ensure pip is available
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True, text=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result.warnings.append(
                "pip not available - try: python -m ensurepip"
            )

        self._repair_path(result)
        self._repair_data_directories(result)

    def _repair_validate(self, result: RecoveryResult) -> None:
        """Repair validation phase issues."""
        self._repair_dependencies(result)
        self._repair_python_path(result)

    def _repair_self_repair(self, result: RecoveryResult) -> None:
        """Repair self-repair phase issues."""
        self._repair_dependencies(result)
        self._repair_path(result)

    def _repair_config(self, result: RecoveryResult) -> None:
        """Repair config loading issues - handles missing and corrupted configs."""
        config_dir = self._project_root / "config"
        config_file = config_dir / "default.yaml"

        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            if config_file.exists():
                # Validate existing config is valid YAML
                try:
                    import yaml
                    with open(config_file, "r", encoding="utf-8") as f:
                        yaml.safe_load(f)
                except (yaml.YAMLError, ValueError, UnicodeDecodeError) as e:
                    # Corrupted config - back up and recreate
                    backup = config_file.with_suffix(".yaml.corrupted")
                    try:
                        import shutil
                        shutil.copy2(config_file, backup)
                        config_file.unlink()
                        result.warnings.append(
                            f"Corrupted config backed up to: {backup.name}"
                        )
                    except Exception:
                        config_file.unlink(missing_ok=True)
                    self._create_default_config(config_file)
                    result.actions.append(RecoveryAction(
                        phase="config",
                        action="Replaced corrupted configuration file",
                        success=True,
                        detail=f"Backup saved as {backup.name}",
                    ))
            else:
                self._create_default_config(config_file)
                result.actions.append(RecoveryAction(
                    phase="config",
                    action="Created default configuration file",
                    success=True,
                ))
        except Exception as e:
            result.errors.append(f"Config repair failed: {e}")

    def _repair_logging(self, result: RecoveryResult) -> None:
        """Repair logging initialization issues."""
        log_dir = self._project_root / "data" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            result.warnings.append(f"Log directory creation failed: {e}")

    def _repair_state(self, result: RecoveryResult) -> None:
        """Repair state initialization issues - fixes dirs and stale temp files."""
        dirs = [
            self._project_root / "data",
            self._project_root / "data" / "persistence",
            self._project_root / "data" / "reports",
        ]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                result.warnings.append(
                    f"Directory creation failed ({d}): {e}"
                )

        # Clean stale temp files from previous runs
        try:
            temp_dirs = [
                self._project_root / "data" / "temp",
                Path(os.environ.get("TEMP", "")) / "corax",
            ]
            for td in temp_dirs:
                if td.exists() and td.is_dir():
                    import time as _time
                    cutoff = _time.time() - 86400  # 24 hours
                    for f in td.iterdir():
                        try:
                            if f.is_file() and f.stat().st_mtime < cutoff:
                                f.unlink()
                        except (PermissionError, OSError):
                            pass
        except Exception:
            pass  # Non-critical cleanup

    def _repair_execution(self, result: RecoveryResult) -> None:
        """Repair execution engine issues."""
        self._repair_python_path(result)
        self._repair_dependencies(result)

    def _repair_deployment(self, result: RecoveryResult) -> None:
        """Repair deployment engine issues."""
        self._repair_python_path(result)
        self._repair_dependencies(result)

    def _repair_reporting(self, result: RecoveryResult) -> None:
        """Repair reporting initialization issues."""
        reports_dir = self._project_root / "data" / "reports"
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            result.warnings.append(
                f"Reports directory creation failed: {e}"
            )

    def _repair_path(self, result: RecoveryResult) -> None:
        """Repair PATH environment variable."""
        repairs = []
        path = os.environ.get("PATH", "")

        # Add Python directory if missing
        python_dir = os.path.dirname(sys.executable)
        if python_dir not in path:
            os.environ["PATH"] = f"{python_dir};{path}"
            repairs.append(f"Added Python directory: {python_dir}")

        # Add Scripts directory if missing (Windows)
        if platform.system() == "Windows":
            scripts_dir = os.path.join(
                os.path.dirname(sys.executable), "Scripts"
            )
            if scripts_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{scripts_dir};{os.environ['PATH']}"
                repairs.append(f"Added Scripts directory: {scripts_dir}")

        if repairs:
            result.actions.append(RecoveryAction(
                phase="path",
                action="PATH repaired",
                success=True,
                detail="; ".join(repairs),
            ))

    def _repair_data_directories(self, result: RecoveryResult) -> None:
        """Repair missing data directories."""
        dirs = [
            self._project_root / "data",
            self._project_root / "data" / "logs",
            self._project_root / "data" / "models",
            self._project_root / "data" / "persistence",
            self._project_root / "data" / "reports",
        ]

        created = []
        for d in dirs:
            try:
                if not d.exists():
                    d.mkdir(parents=True, exist_ok=True)
                    created.append(d.name)
            except Exception as e:
                result.warnings.append(
                    f"Could not create {d}: {e}"
                )

        if created:
            result.actions.append(RecoveryAction(
                phase="data_dirs",
                action=f"Created directories: {', '.join(created)}",
                success=True,
            ))

    def _repair_dependencies(self, result: RecoveryResult) -> None:
        """Repair missing dependencies."""
        req_file = self._project_root / "requirements.txt"
        if not req_file.exists():
            return

        try:
            # Check which dependencies are missing
            pip_result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True, text=True, timeout=30,
            )
            if pip_result.returncode != 0:
                result.warnings.append(
                    f"pip list failed (exit {pip_result.returncode}): "
                    f"{pip_result.stderr[:200]}"
                )
                return
            installed = {
                pkg["name"].lower()
                for pkg in json.loads(pip_result.stdout)
            }

            missing = []
            with open(req_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    for sep in [">=", "==", "<=", "~=", "!="]:
                        if sep in line:
                            line = line.split(sep)[0]
                            break
                    pkg_name = line.strip().lower()
                    if pkg_name and pkg_name not in installed:
                        missing.append(line)

            if missing:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install"] + missing,
                    check=True, capture_output=True, text=True, timeout=300,
                )
                result.actions.append(RecoveryAction(
                    phase="dependencies",
                    action=f"Installed {len(missing)} missing dependencies",
                    success=True,
                ))
        except Exception as e:
            result.errors.append(f"Dependency repair failed: {e}")

    def _repair_python_path(self, result: RecoveryResult) -> None:
        """Repair Python path to include project root."""
        project_root_str = str(self._project_root)
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)
            result.actions.append(RecoveryAction(
                phase="python_path",
                action="Added project root to Python path",
                success=True,
            ))

    def _create_default_config(self, path: Path) -> None:
        """Create a default configuration file."""
        default_config = """# Corax Orchestrator - Default Configuration
# Auto-generated by StartupRecovery

app:
  name: CoraxOrchestrator
  version: 1.0.0-alpha
  debug: false
  log_level: INFO

paths:
  data_dir: data
  log_dir: data/logs
  model_dir: data/models
  persistence_dir: data/persistence
  reports_dir: data/reports

deployment:
  max_concurrent: 3
  timeout_seconds: 300
  retry_attempts: 3
  verify_after_deploy: true

ai:
  default_provider: ollama
  providers:
    ollama:
      base_url: http://localhost:11434
      timeout: 60
    lm_studio:
      base_url: http://localhost:1234
      timeout: 60

logging:
  version: 1
  formatters:
    standard:
      format: '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  handlers:
    console:
      class: logging.StreamHandler
      level: INFO
      formatter: standard
    file:
      class: logging.FileHandler
      level: DEBUG
      formatter: standard
      filename: data/logs/corax.log
  root:
    level: INFO
    handlers: [console, file]
"""
        path.write_text(default_config, encoding="utf-8")
