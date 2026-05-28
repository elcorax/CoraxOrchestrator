"""
Corax Orchestrator — Runtime Snapshot Exporter (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- runtime-state snapshot export
- lightweight validation summaries
- runtime snapshot generation

Usage:
    python validation/runtime_snapshot_exporter.py [--output DIR]
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


class SnapshotResult:
    """Result of a snapshot export operation."""

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


class RuntimeSnapshotExporter:
    """
    Lightweight runtime state snapshot export utility.

    Captures:
    - Current runtime state snapshot
    - System information snapshot
    - Module load state
    - Environment variables
    - Diagnostic status
    - Generates validation summaries
    """

    def __init__(self, output_dir: Optional[str] = None):
        self._results: List[SnapshotResult] = []
        self._start_time = time.time()
        self._output_dir = Path(output_dir) if output_dir else (
            _project_root / "data" / "reports" / "snapshots"
        )
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def run_all(self) -> Dict[str, Any]:
        """Run all snapshot export operations."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Runtime Snapshot Exporter{RESET}")
        print(f"{'=' * 60}")
        print(f"Output dir: {self._output_dir}")
        print(f"Python:     {sys.version.split()[0]}")
        print(f"Platform:   {sys.platform}")
        print(f"{'=' * 60}\n")

        self._export_runtime_state_snapshot()
        self._export_system_snapshot()
        self._export_module_snapshot()
        self._export_environment_snapshot()
        self._export_validation_summary()

        self._print_summary()
        return self._generate_report()

    def _export_runtime_state_snapshot(self) -> None:
        """Export current runtime state snapshot."""
        result = SnapshotResult("runtime_state_snapshot")
        start = time.time()

        try:
            # Try to get runtime state from diagnostics
            runtime_state = {}
            try:
                from src.runtime.diagnostics import RuntimeDiagnostics
                rt_diag = RuntimeDiagnostics()
                rt_report = rt_diag.finalize(success=True)
                runtime_state["runtime_diagnostics_available"] = True
                runtime_state["system_info"] = rt_report.system_info
            except ImportError:
                runtime_state["runtime_diagnostics_available"] = False

            # Get health diagnostics
            try:
                from src.health.diagnostics import StartupDiagnostics
                diag = StartupDiagnostics()
                diag.collect_system_info()
                diag.start_phase("snapshot_export")
                diag.end_phase("snapshot_export", "success")
                health_report = diag.finalize(success=True)
                runtime_state["health_diagnostics_available"] = True
                runtime_state["health_system_info"] = health_report.system_info
            except ImportError:
                runtime_state["health_diagnostics_available"] = False

            # Compile snapshot
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "runtime_state": runtime_state,
                "python_version": sys.version,
                "platform": sys.platform,
                "pid": os.getpid(),
                "cwd": os.getcwd(),
            }

            # Save snapshot
            snap_path = self._output_dir / f"runtime_state_{int(time.time())}.json"
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "snapshot_captured": True,
                "saved_to": str(snap_path),
                "file_size_bytes": snap_path.stat().st_size,
                "runtime_diagnostics": runtime_state.get("runtime_diagnostics_available", False),
                "health_diagnostics": runtime_state.get("health_diagnostics_available", False),
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Runtime state snapshot failed: {e}"

        self._results.append(result)
        self._print_result(result)

    def _export_system_snapshot(self) -> None:
        """Export system information snapshot."""
        result = SnapshotResult("system_snapshot")
        start = time.time()

        try:
            import platform as plat

            system_snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system": plat.system(),
                "node": plat.node(),
                "release": plat.release(),
                "version": plat.version(),
                "machine": plat.machine(),
                "processor": plat.processor(),
                "python_build": plat.python_build(),
                "python_compiler": plat.python_compiler(),
            }

            # Try psutil for extended info
            try:
                import psutil
                system_snapshot["cpu_count"] = psutil.cpu_count()
                system_snapshot["cpu_percent"] = psutil.cpu_percent(interval=0.1)
                system_snapshot["memory_total_gb"] = round(
                    psutil.virtual_memory().total / (1024**3), 2
                )
                system_snapshot["memory_available_gb"] = round(
                    psutil.virtual_memory().available / (1024**3), 2
                )
                system_snapshot["memory_percent"] = psutil.virtual_memory().percent
                system_snapshot["disk_usage_gb"] = round(
                    psutil.disk_usage("/").used / (1024**3), 2
                ) if sys.platform != "win32" else "N/A (Windows)"
            except ImportError:
                system_snapshot["psutil_available"] = False

            snap_path = self._output_dir / f"system_snapshot_{int(time.time())}.json"
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(system_snapshot, f, indent=2, default=str)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "snapshot_saved": str(snap_path),
                "system": system_snapshot.get("system"),
                "python_version": system_snapshot.get("python_build", [""])[0],
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"System snapshot failed: {e}"

        self._results.append(result)
        self._print_result(result)

    def _export_module_snapshot(self) -> None:
        """Export module load state snapshot."""
        result = SnapshotResult("module_snapshot")
        start = time.time()

        try:
            all_modules = sorted(sys.modules.keys())
            src_modules = sorted([m for m in all_modules if m.startswith("src.")])
            test_modules = sorted([m for m in all_modules if m.startswith("test") or m.startswith("validation.")])

            module_snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_modules": len(all_modules),
                "src_modules": len(src_modules),
                "test_modules": len(test_modules),
                "src_module_list": src_modules,
                "test_module_list": test_modules,
            }

            snap_path = self._output_dir / f"module_snapshot_{int(time.time())}.json"
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(module_snapshot, f, indent=2, default=str)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "snapshot_saved": str(snap_path),
                "total_modules": len(all_modules),
                "src_modules": len(src_modules),
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Module snapshot failed: {e}"

        self._results.append(result)
        self._print_result(result)

    def _export_environment_snapshot(self) -> None:
        """Export environment variable snapshot."""
        result = SnapshotResult("environment_snapshot")
        start = time.time()

        try:
            # Collect relevant environment variables
            env_snapshot = {}
            for key, value in sorted(os.environ.items()):
                # Filter relevant vars to keep snapshot manageable
                if any(kw in key.upper() for kw in ["CORAX", "PATH", "PYTHON", "HOME", "USER", "TEMP", "TMP", "SYSTEM"]):
                    env_snapshot[key] = value

            env_snapshot["_meta"] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_env_vars": len(os.environ),
                "captured_vars": len(env_snapshot),
            }

            snap_path = self._output_dir / f"environment_snapshot_{int(time.time())}.json"
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(env_snapshot, f, indent=2, default=str)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "snapshot_saved": str(snap_path),
                "total_env_vars": len(os.environ),
                "captured_relevant_vars": len(env_snapshot) - 1,  # exclude _meta
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Environment snapshot failed: {e}"

        self._results.append(result)
        self._print_result(result)

    def _export_validation_summary(self) -> None:
        """Generate and export a lightweight validation summary."""
        result = SnapshotResult("validation_summary")
        start = time.time()

        try:
            # Compile a summary of all snapshots taken
            snapshot_files = list(self._output_dir.glob("*.json"))
            total_snapshots = len(snapshot_files)
            total_size = sum(f.stat().st_size for f in snapshot_files)

            summary = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool": "runtime_snapshot_exporter.py",
                "snapshot_directory": str(self._output_dir),
                "total_snapshots": total_snapshots,
                "total_size_bytes": total_size,
                "total_size_kb": round(total_size / 1024, 1),
                "snapshots": [
                    {
                        "name": f.name,
                        "size_bytes": f.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                    for f in snapshot_files
                ],
            }

            summary_path = self._output_dir / "snapshot_summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, default=str)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "summary_saved": str(summary_path),
                "total_snapshots": total_snapshots,
                "total_size_kb": round(total_size / 1024, 1),
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Validation summary export failed: {e}"

        self._results.append(result)
        self._print_result(result)

    def _print_result(self, result: SnapshotResult) -> None:
        """Print a single snapshot result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {result.name} ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"         {YELLOW}Error: {result.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the snapshot export summary."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Runtime Snapshot Export Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total snapshots: {total}")
        print(f"  Passed:          {GREEN}{passed}{RESET}")
        print(f"  Failed:          {RED}{total - passed}{RESET}")
        print(f"  Duration:        {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL SNAPSHOT EXPORTS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME SNAPSHOTS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete snapshot export report."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)

        return {
            "runtime_snapshot_export_report": {
                "tool": "runtime_snapshot_exporter.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "output_directory": str(self._output_dir),
                "total_snapshots": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "results": [r.to_dict() for r in self._results],
            }
        }


def main() -> int:
    """Run the runtime snapshot exporter."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Runtime Snapshot Exporter"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory for snapshots"
    )
    args = parser.parse_args()

    exporter = RuntimeSnapshotExporter(output_dir=args.output)
    report = exporter.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "runtime_snapshot_export_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["runtime_snapshot_export_report"]["passed"]
    total = report["runtime_snapshot_export_report"]["total_snapshots"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
