"""
Corax Orchestrator - Runtime Diagnostics.

Provides comprehensive runtime diagnostics including startup logs,
bootstrap logs, dependency diagnostics, environment diagnostics,
and crash diagnostics. Every failure is actionable and every
startup phase is observable.

Survivability-hardened: safe startup logging, missing-state safety,
bounded diagnostics, partial-runtime support.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import sys
import tempfile
import traceback
import warnings
from pathlib import Path


def _is_frozen() -> bool:
    """Detect if running as a PyInstaller executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _safe_str(value: Any, default: str = "") -> str:
    """Safely convert any value to string."""
    try:
        return str(value)
    except Exception:
        return default


@dataclass
class RuntimeDiagnosticReport:
    """Complete runtime diagnostic report."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    success: bool = False
    phases: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    system_info: Dict[str, Any] = field(default_factory=dict)
    dependency_status: Dict[str, str] = field(default_factory=dict)
    performance: Dict[str, float] = field(default_factory=dict)
    crash_info: Optional[Dict[str, Any]] = None
    recovery_actions: List[str] = field(default_factory=list)
    frozen_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        try:
            return {
                "timestamp": self.timestamp,
                "success": self.success,
                "phases": self.phases,
                "errors": self.errors,
                "warnings": self.warnings,
                "system_info": self.system_info,
                "dependency_status": self.dependency_status,
                "performance": self.performance,
                "crash_info": self.crash_info,
                "recovery_actions": self.recovery_actions,
                "frozen_detected": self.frozen_detected,
            }
        except Exception:
            return {"success": False, "error": "Failed to serialize report"}

    def to_json(self, indent: int = 2) -> str:
        try:
            return json.dumps(self.to_dict(), indent=indent, default=str)
        except Exception:
            return '{"success": false, "error": "JSON serialization failed"}'

    def to_markdown(self) -> str:
        """Generate a markdown diagnostic report."""
        try:
            lines = [
                "# Corax Orchestrator — Runtime Diagnostic Report",
                "",
                f"**Generated:** {self.timestamp}",
                f"**Status:** {'✅ SUCCESS' if self.success else '❌ FAILED'}",
                "",
                "---",
                "",
                "## System Information",
                "",
            ]
            for key, value in self.system_info.items():
                lines.append(f"- **{key}:** {_safe_str(value)}")

            lines.extend(["", "---", "", "## Startup Phases", ""])
            for phase_name, phase_data in self.phases.items():
                status = phase_data.get("status", "unknown")
                duration = phase_data.get("duration_ms", "N/A")
                icon = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
                lines.append(f"### {icon} {phase_name}")
                lines.append(f"- **Status:** {status}")
                lines.append(f"- **Duration:** {duration}ms")
                if phase_data.get("errors"):
                    for err in phase_data["errors"]:
                        lines.append(f"- **Error:** {err}")
                lines.append("")

            if self.errors:
                lines.extend(["---", "", "## Errors", ""])
                for err in self.errors:
                    lines.append(f"- **{err.get('phase', 'unknown')}:** {err.get('message', '')}")
                    if err.get("detail"):
                        lines.append(f"  - {err['detail']}")
                lines.append("")

            if self.warnings:
                lines.extend(["---", "", "## Warnings", ""])
                for w in self.warnings:
                    lines.append(f"- {w}")
                lines.append("")

            if self.dependency_status:
                lines.extend([
                    "---", "", "## Dependency Status", "",
                    "| Dependency | Status |",
                    "|------------|--------|",
                ])
                for dep, status in self.dependency_status.items():
                    icon = "✅" if status == "ok" else "❌"
                    lines.append(f"| {dep} | {icon} {status} |")
                lines.append("")

            if self.performance:
                lines.extend(["---", "", "## Performance", ""])
                for key, value in self.performance.items():
                    lines.append(f"- **{key}:** {value:.2f}s")
                lines.append("")

            if self.crash_info:
                lines.extend([
                    "---", "", "## 🚨 Crash Diagnostics", "",
                    f"- **Type:** {self.crash_info.get('type', 'unknown')}",
                    f"- **Message:** {self.crash_info.get('message', '')}",
                    "", "### Traceback", "", "```",
                    self.crash_info.get("traceback", ""),
                    "```", "",
                ])

            if self.recovery_actions:
                lines.extend(["---", "", "## Recovery Actions", ""])
                for action in self.recovery_actions:
                    lines.append(f"- {action}")
                lines.append("")

            lines.extend(["---", "", "*Report generated by Corax Runtime Diagnostics*"])
            return "\n".join(lines)
        except Exception:
            return "# Diagnostic Report - Generation Failed"


class RuntimeDiagnostics:
    """
    Runtime diagnostics and observability system.

    Tracks startup phases, collects system information, validates
    dependencies, captures crash information, and generates
    actionable diagnostic reports.

    Survivability:
    - Bounded diagnostics: never crashes on missing state
    - Crash-safe reporting: JSON/markdown generation is guarded
    - Missing-state safety: all accessors return defaults
    - Partial-runtime support: works even if kernel not fully initialized
    """

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = Path(project_root or os.getcwd())
        self._report = RuntimeDiagnosticReport()
        self._report.frozen_detected = _is_frozen()
        self._phase_timers: Dict[str, datetime] = {}
        self._start_time = datetime.now(timezone.utc)

        # Collect system info (guarded)
        try:
            self._collect_system_info()
        except Exception:
            self._report.system_info = {"error": "Failed to collect system info"}

    def _collect_system_info(self) -> None:
        """Collect system information for diagnostics."""
        try:
            info = {
                "platform": platform.platform(),
                "platform_system": platform.system(),
                "platform_release": platform.release(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "python_version": sys.version.split()[0],
                "python_executable": sys.executable,
                "hostname": platform.node(),
                "cwd": os.getcwd(),
                "pid": os.getpid(),
                "frozen": _is_frozen(),
            }

            try:
                import psutil  # noqa: F401
                info["cpu_count"] = psutil.cpu_count()
                info["memory_total_gb"] = round(
                    psutil.virtual_memory().total / (1024**3), 2
                )
                info["memory_available_gb"] = round(
                    psutil.virtual_memory().available / (1024**3), 2
                )
            except ImportError:
                info["cpu_count"] = os.cpu_count()

            self._report.system_info = info
        except Exception:
            self._report.system_info = {"error": "System info collection failed"}

    def start_phase(self, phase: str) -> None:
        """Start timing a startup phase."""
        try:
            self._phase_timers[phase] = datetime.now(timezone.utc)
        except Exception:
            pass

    def end_phase(
        self,
        phase: str,
        status: str = "success",
        errors: Optional[List[str]] = None,
    ) -> None:
        """End timing a startup phase and record results."""
        try:
            start = self._phase_timers.get(phase)
            duration_ms = 0.0
            if start:
                duration_ms = (
                    datetime.now(timezone.utc) - start
                ).total_seconds() * 1000

            self._report.phases[phase] = {
                "status": status,
                "duration_ms": round(duration_ms, 2),
                "errors": errors or [],
            }
            self._report.performance[phase] = duration_ms / 1000

            if status == "failed" and errors:
                for err in errors:
                    self._report.errors.append({
                        "phase": phase,
                        "message": str(err),
                    })
        except Exception:
            pass

    def check_dependencies(
        self, dependencies: Dict[str, str]
    ) -> Dict[str, str]:
        """Check if required dependencies are available."""
        status: Dict[str, str] = {}
        try:
            for dep_name, import_path in dependencies.items():
                try:
                    __import__(import_path)
                    status[dep_name] = "ok"
                except ImportError:
                    status[dep_name] = "missing"
                    self._report.warnings.append(
                        f"Dependency '{dep_name}' ({import_path}) is missing"
                    )

            self._report.dependency_status = status
        except Exception:
            pass
        return status

    def record_error(
        self, phase: str, message: str, detail: str = ""
    ) -> None:
        """Record an error in the diagnostic report."""
        try:
            self._report.errors.append({
                "phase": phase,
                "message": str(message),
                "detail": str(detail),
            })
        except Exception:
            pass

    def record_warning(self, message: str) -> None:
        """Record a warning in the diagnostic report."""
        try:
            self._report.warnings.append(str(message))
        except Exception:
            pass

    def record_recovery(self, action: str) -> None:
        """Record a recovery action."""
        try:
            self._report.recovery_actions.append(str(action))
        except Exception:
            pass

    def capture_crash(self) -> None:
        """Capture crash information from current exception."""
        try:
            exc_info = sys.exc_info()
            if exc_info and exc_info[0]:
                tb = "".join(traceback.format_exception(*exc_info))
                self._report.crash_info = {
                    "type": exc_info[0].__name__,
                    "message": str(exc_info[1]),
                    "traceback": tb,
                }
        except Exception:
            pass

    def finalize(self, success: bool = True) -> RuntimeDiagnosticReport:
        """Finalize the diagnostic report."""
        try:
            self._report.success = success
            total_time = (
                datetime.now(timezone.utc) - self._start_time
            ).total_seconds()
            self._report.performance["total_startup_time"] = round(total_time, 2)
        except Exception:
            pass
        return self._report

    def save_report(self, filename: Optional[str] = None) -> str:
        """Save the diagnostic report to a file."""
        try:
            if filename is None:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                filename = f"runtime_diagnostics_{ts}.json"

            log_dir = self._project_root / "data" / "logs"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                log_dir = Path(os.getcwd()) / "_corax_logs"
                log_dir.mkdir(parents=True, exist_ok=True)

            filepath = log_dir / filename
            filepath.write_text(
                self._report.to_json(), encoding="utf-8"
            )

            # Also save markdown version
            try:
                md_filename = filename.replace(".json", ".md")
                md_filepath = log_dir / md_filename
                md_filepath.write_text(
                    self._report.to_markdown(), encoding="utf-8"
                )
            except Exception:
                pass

            return str(filepath)
        except Exception:
            return ""

    def get_report(self) -> RuntimeDiagnosticReport:
        """Get the current diagnostic report."""
        return self._report
