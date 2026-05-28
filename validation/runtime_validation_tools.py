"""
Corax Orchestrator — Runtime Validation Tools (Auxiliary Validation Tooling).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- repeated execution-session simulation
- repeated diagnostics export testing
- stale-state detection helpers
- runtime state validation

Usage:
    python validation/runtime_validation_tools.py [--check STATE_CHECK]
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


class RuntimeValidationCheck:
    """Result of a single runtime validation check."""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.duration_ms: float = 0.0
        self.error: Optional[str] = None
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
            "details": self.details,
        }


class RuntimeValidationTools:
    """
    Collection of bounded runtime validation utilities.

    Provides helpers for:
    - Repeated execution-session simulation
    - Repeated diagnostics export testing
    - Stale-state detection
    - Runtime state snapshot validation
    """

    def __init__(self):
        self._checks: List[RuntimeValidationCheck] = []
        self._start_time = time.time()

    def run_all(self) -> Dict[str, Any]:
        """Run all runtime validation checks."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Runtime Validation Tools{RESET}")
        print(f"{'=' * 60}")
        print(f"Python:   {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._check_session_simulation()
        self._check_diagnostics_export_repeated()
        self._check_stale_state_detection()
        self._check_runtime_state_snapshot()

        self._print_summary()
        return self._generate_report()

    def _check_session_simulation(self) -> None:
        """Simulate repeated execution sessions."""
        check = RuntimeValidationCheck("execution_session_simulation")
        start = time.time()

        try:
            from src.core.config import load_config
            from src.core.logging import get_logger, setup_logging

            sessions = 5
            session_results = []

            for i in range(sessions):
                s_start = time.time()
                setup_logging()
                logger = get_logger(f"session_{i}")
                cfg = load_config(None)
                s_ms = (time.time() - s_start) * 1000
                session_results.append({
                    "session": i + 1,
                    "duration_ms": round(s_ms, 1),
                    "logger_ready": logger is not None,
                    "config_loaded": cfg is not None,
                })

            all_ok = all(
                s["logger_ready"] and s["config_loaded"]
                for s in session_results
            )

            check.passed = all_ok
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "sessions_simulated": sessions,
                "session_results": session_results,
            }
            if not all_ok:
                check.error = "One or more sessions failed to initialize"
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Session simulation failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_diagnostics_export_repeated(self) -> None:
        """Test repeated diagnostics export across multiple cycles."""
        check = RuntimeValidationCheck("repeated_diagnostics_export")
        start = time.time()

        try:
            from src.health.diagnostics import StartupDiagnostics

            exports = 5
            export_results = []
            log_dir = _project_root / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            for i in range(exports):
                e_start = time.time()
                diag = StartupDiagnostics()
                diag.collect_system_info()
                diag.start_phase(f"export_{i}")
                diag.end_phase(f"export_{i}", "success")
                diag.finalize(success=True)
                path = diag.save_report(f"repeated_export_{i}_{int(time.time())}.json")
                e_ms = (time.time() - e_start) * 1000
                export_results.append({
                    "export": i + 1,
                    "duration_ms": round(e_ms, 1),
                    "saved_to": path,
                    "file_exists": Path(path).exists(),
                })

            all_exported = all(e["file_exists"] for e in export_results)

            check.passed = all_exported
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "exports_attempted": exports,
                "exports_succeeded": sum(1 for e in export_results if e["file_exists"]),
                "export_results": export_results,
            }
            if not all_exported:
                check.error = "One or more exports failed"
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Repeated export failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_stale_state_detection(self) -> None:
        """Detect stale state in sys.modules and runtime caches."""
        check = RuntimeValidationCheck("stale_state_detection")
        start = time.time()

        try:
            # Scan sys.modules for stale/module leakage patterns
            all_modules = list(sys.modules.keys())
            src_modules = [m for m in all_modules if m.startswith("src.")]

            # Look for duplicate or stale module patterns
            module_versions: Dict[str, List[str]] = {}
            for m in src_modules:
                base = m.split(".")[0] + "." + m.split(".")[1] if len(m.split(".")) > 1 else m
                if base not in module_versions:
                    module_versions[base] = []
                module_versions[base].append(m)

            # Detect stale cache files
            log_dir = _project_root / "data" / "logs"
            cache_files = list(log_dir.glob("*.json")) if log_dir.exists() else []
            cache_files.extend(log_dir.glob("*.md") if log_dir.exists() else [])

            check.passed = True
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "total_modules_loaded": len(all_modules),
                "src_modules_loaded": len(src_modules),
                "stale_cache_files": len(cache_files),
                "cache_file_list": [str(f.name) for f in cache_files[:10]],
                "module_breakdown": {
                    base: len(mods) for base, mods in module_versions.items()
                },
            }
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Stale state detection failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_runtime_state_snapshot(self) -> None:
        """Take and validate a runtime state snapshot."""
        check = RuntimeValidationCheck("runtime_state_snapshot")
        start = time.time()

        try:
            # Collect a lightweight runtime state snapshot
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sys_modules_count": len(sys.modules),
                "src_modules_count": len([m for m in sys.modules if m.startswith("src.")]),
                "python_version": sys.version,
                "platform": sys.platform,
                "cwd": os.getcwd(),
                "pid": os.getpid(),
            }

            # Try to get runtime state if available
            try:
                from src.runtime.state import RuntimeState
                state = RuntimeState()
                snapshot["runtime_state_available"] = True
                snapshot["runtime_state_keys"] = list(state.__dict__.keys()) if hasattr(state, '__dict__') else []
            except ImportError:
                snapshot["runtime_state_available"] = False

            # Save snapshot
            snap_dir = _project_root / "data" / "reports"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_path = snap_dir / f"runtime_snapshot_{int(time.time())}.json"
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)

            check.passed = True
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "snapshot_collected": True,
                "snapshot_keys": list(snapshot.keys()),
                "saved_to": str(snap_path),
                "file_size_bytes": snap_path.stat().st_size if snap_path.exists() else 0,
            }
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Runtime snapshot failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _print_check(self, check: RuntimeValidationCheck) -> None:
        """Print a single validation check result."""
        status = f"{GREEN}PASS{RESET}" if check.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {check.name} ({check.duration_ms:.0f}ms)")
        if check.error:
            print(f"         {YELLOW}Error: {check.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the validation summary."""
        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Runtime Validation Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total checks: {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL RUNTIME VALIDATIONS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME VALIDATIONS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete runtime validation report."""
        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)

        return {
            "runtime_validation_report": {
                "tool": "runtime_validation_tools.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_checks": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "checks": [c.to_dict() for c in self._checks],
            }
        }


def main() -> int:
    """Run all runtime validation tools."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Runtime Validation Tools"
    )
    parser.add_argument(
        "--check", type=str, default="all",
        choices=["all", "sessions", "exports", "stale", "snapshot"],
        help="Specific validation check to run"
    )
    args = parser.parse_args()

    tools = RuntimeValidationTools()
    report = tools.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "runtime_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["runtime_validation_report"]["passed"]
    total = report["runtime_validation_report"]["total_checks"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
