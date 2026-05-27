"""
Corax Orchestrator - Startup Diagnostics System.

Provides executable diagnostics including startup logs,
runtime diagnostics, dependency diagnostics, crash diagnostics,
and bootstrap diagnostics. Ensures failures are actionable
and startup problems are traceable.
"""

from typing import Dict, Any, List, Optional, TextIO
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import subprocess
import sys
import textwrap
import traceback
from pathlib import Path


@dataclass
class DiagnosticReport:
    """Complete diagnostic report for executable startup."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    success: bool = False
    phase: str = "initialization"

    # System info
    system_info: Dict[str, Any] = field(default_factory=dict)

    # Startup phases
    bootstrap_phase: Dict[str, Any] = field(default_factory=dict)
    runtime_phase: Dict[str, Any] = field(default_factory=dict)
    deployment_phase: Dict[str, Any] = field(default_factory=dict)
    ai_provisioning_phase: Dict[str, Any] = field(default_factory=dict)

    # Diagnostics
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    performance: Dict[str, float] = field(default_factory=dict)

    # Dependency diagnostics
    dependency_status: Dict[str, str] = field(default_factory=dict)

    # Crash diagnostics
    crash_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "success": self.success,
            "phase": self.phase,
            "system_info": self.system_info,
            "bootstrap_phase": self.bootstrap_phase,
            "runtime_phase": self.runtime_phase,
            "deployment_phase": self.deployment_phase,
            "ai_provisioning_phase": self.ai_provisioning_phase,
            "errors": self.errors,
            "warnings": self.warnings,
            "performance": self.performance,
            "dependency_status": self.dependency_status,
            "crash_info": self.crash_info,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Generate a markdown diagnostic report."""
        lines = [
            "# Corax Orchestrator — Startup Diagnostics Report",
            "",
            f"**Generated:** {self.timestamp}",
            f"**Status:** {'✅ SUCCESS' if self.success else '❌ FAILED'}",
            f"**Phase:** {self.phase}",
            "",
            "---",
            "",
            "## System Information",
            "",
        ]

        for key, value in self.system_info.items():
            lines.append(f"- **{key}:** {value}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Startup Phases")
        lines.append("")

        phases = [
            ("Bootstrap", self.bootstrap_phase),
            ("Runtime", self.runtime_phase),
            ("Deployment", self.deployment_phase),
            ("AI Provisioning", self.ai_provisioning_phase),
        ]

        for name, phase_data in phases:
            status = phase_data.get("status", "unknown")
            duration = phase_data.get("duration_ms", "N/A")
            icon = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
            lines.append(f"### {icon} {name} Phase")
            lines.append("")
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
                if err.get("traceback"):
                    lines.append(f"  ```")
                    lines.append(f"  {err['traceback']}")
                    lines.append(f"  ```")
            lines.append("")

        if self.warnings:
            lines.extend(["---", "", "## Warnings", ""])
            for warning in self.warnings:
                lines.append(f"- {warning.get('message', '')}")
            lines.append("")

        if self.dependency_status:
            lines.extend([
                "---",
                "",
                "## Dependency Status",
                "",
                "| Dependency | Status |",
                "|------------|--------|",
            ])
            for dep, status in self.dependency_status.items():
                icon = "✅" if status == "ok" else "❌" if status == "missing" else "⚠️"
                lines.append(f"| {dep} | {icon} {status} |")
            lines.append("")

        if self.performance:
            lines.extend([
                "---",
                "",
                "## Performance",
                "",
            ])
            for key, value in self.performance.items():
                lines.append(f"- **{key}:** {value:.2f}s")
            lines.append("")

        if self.crash_info:
            lines.extend([
                "---",
                "",
                "## 🚨 Crash Diagnostics",
                "",
                f"- **Type:** {self.crash_info.get('type', 'unknown')}",
                f"- **Message:** {self.crash_info.get('message', '')}",
                "",
                "### Traceback",
                "",
                "```",
                f"{self.crash_info.get('traceback', '')}",
                "```",
                "",
            ])

        lines.append("---")
        lines.append("")
        lines.append("*Report generated by Corax Orchestrator Diagnostics System*")
        return "\n".join(lines)


class StartupDiagnostics:
    """
    Provides comprehensive startup diagnostics for the Corax executable.

    Tracks startup phases, collects system information, validates
    dependencies, and captures crash information for actionable
    failure analysis.
    """

    def __init__(self, log_dir: Optional[str] = None):
        self._report = DiagnosticReport()
        self._log_dir = log_dir or os.path.join(
            os.getcwd(), "data", "logs"
        )
        self._start_time = datetime.now(timezone.utc)
        self._phase_timers: Dict[str, datetime] = {}

        # Ensure log directory exists
        os.makedirs(self._log_dir, exist_ok=True)

    def collect_system_info(self) -> Dict[str, Any]:
        """Collect system information for diagnostics."""
        info = {
            "platform": platform.platform(),
            "platform_system": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "hostname": platform.node(),
            "cwd": os.getcwd(),
            "pid": os.getpid(),
        }

        # Try to get more system info
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
            info["memory_info"] = "psutil not available"

        self._report.system_info = info
        return info

    def start_phase(self, phase: str) -> None:
        """Start timing a startup phase."""
        self._phase_timers[phase] = datetime.now(timezone.utc)
        self._report.phase = phase

    def end_phase(self, phase: str, status: str = "success",
                  errors: Optional[List[str]] = None) -> None:
        """End timing a startup phase and record results."""
        start = self._phase_timers.get(phase)
        if start:
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        else:
            duration_ms = 0

        phase_data = {
            "status": status,
            "duration_ms": round(duration_ms, 2),
            "errors": errors or [],
        }

        phase_key = f"{phase.lower().replace(' ', '_')}_phase"
        if hasattr(self._report, phase_key):
            setattr(self._report, phase_key, phase_data)

        # Track performance
        self._report.performance[phase] = duration_ms / 1000

        if status == "failed":
            self._report.success = False
            if errors:
                for err in errors:
                    self._report.errors.append({
                        "phase": phase,
                        "message": err,
                        "detail": "",
                    })

    def check_dependencies(self, dependencies: Dict[str, str]) -> Dict[str, str]:
        """Check if required dependencies are available."""
        status: Dict[str, str] = {}

        for dep_name, import_path in dependencies.items():
            try:
                __import__(import_path)
                status[dep_name] = "ok"
            except ImportError:
                status[dep_name] = "missing"
                self._report.warnings.append({
                    "message": f"Dependency '{dep_name}' ({import_path}) is missing",
                })

        self._report.dependency_status = status
        return status

    def record_error(self, phase: str, message: str, detail: str = "",
                     tb: Optional[str] = None) -> None:
        """Record an error in the diagnostic report."""
        self._report.errors.append({
            "phase": phase,
            "message": message,
            "detail": detail,
            "traceback": tb or "",
        })
        self._report.success = False

    def record_warning(self, message: str) -> None:
        """Record a warning in the diagnostic report."""
        self._report.warnings.append({"message": message})

    def capture_crash(self, exc_info: Optional[Any] = None) -> None:
        """Capture crash information from an exception."""
        if exc_info is None:
            exc_info = sys.exc_info()

        if exc_info and exc_info[0]:
            tb = "".join(traceback.format_exception(*exc_info))
            self._report.crash_info = {
                "type": exc_info[0].__name__,
                "message": str(exc_info[1]),
                "traceback": tb,
            }
            self._report.success = False

    def finalize(self, success: bool = True) -> DiagnosticReport:
        """Finalize the diagnostic report."""
        self._report.success = success
        total_time = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        self._report.performance["total_startup_time"] = round(total_time, 2)
        return self._report

    def save_report(self, filename: Optional[str] = None) -> str:
        """Save the diagnostic report to a file."""
        if filename is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"startup_diagnostics_{ts}.json"

        filepath = os.path.join(self._log_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self._report.to_json())

        # Also save markdown version
        md_filename = filename.replace(".json", ".md")
        md_filepath = os.path.join(self._log_dir, md_filename)
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(self._report.to_markdown())

        return filepath

    def get_report(self) -> DiagnosticReport:
        """Get the current diagnostic report."""
        return self._report

    @staticmethod
    def load_report(filepath: str) -> DiagnosticReport:
        """Load a diagnostic report from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        report = DiagnosticReport()
        for key, value in data.items():
            if hasattr(report, key):
                setattr(report, key, value)
        return report
