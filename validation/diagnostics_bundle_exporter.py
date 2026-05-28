"""
Corax Orchestrator — Diagnostics Bundle Exporter (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- diagnostics collection
- log export automation
- crash-report bundling
- repeated diagnostics export

Usage:
    python validation/diagnostics_bundle_exporter.py [--clean]
"""

import sys
import os
import time
import json
import shutil
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


class BundleExportResult:
    """Result of a diagnostics bundle export operation."""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: Optional[str] = None
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "error": self.error,
            "details": self.details,
        }


class DiagnosticsBundleExporter:
    """
    Lightweight diagnostics/log aggregation and bundling utility.

    Collects:
    - Runtime diagnostic reports
    - Startup diagnostic reports
    - Log files from data/logs/
    - Crash reports
    - Environment snapshots
    - Bundles everything into a timestamped export archive
    """

    def __init__(self, clean_after: bool = False):
        self._results: List[BundleExportResult] = []
        self._start_time = time.time()
        self._clean_after = clean_after
        self._bundle_dir: Optional[Path] = None

    def run_all(self) -> Dict[str, Any]:
        """Run all bundle export operations."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Diagnostics Bundle Exporter{RESET}")
        print(f"{'=' * 60}")
        print(f"Clean after: {self._clean_after}")
        print(f"Python:      {sys.version.split()[0]}")
        print(f"Platform:    {sys.platform}")
        print(f"{'=' * 60}\n")

        self._export_bundle_diagnostics()
        self._export_log_collection()
        self._export_crash_report_bundle()
        self._export_runtime_snapshots()
        self._verify_bundle_integrity()

        self._print_summary()
        return self._generate_report()

    def _export_bundle_diagnostics(self) -> None:
        """Export a bundled diagnostics report."""
        result = BundleExportResult("diagnostics_bundle_export")
        try:
            from src.health.diagnostics import StartupDiagnostics

            diag = StartupDiagnostics()
            diag.collect_system_info()

            # Generate comprehensive diagnostics
            diag.start_phase("bundle_export")
            diag.check_dependencies({
                "PyYAML": "yaml",
                "requests": "requests",
                "psutil": "psutil",
            })
            diag.end_phase("bundle_export", "success")
            report = diag.finalize(success=True)

            # Save to bundle directory
            bundle_dir = _project_root / "data" / "reports" / "bundles"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            self._bundle_dir = bundle_dir

            ts = int(time.time())
            report_path = bundle_dir / f"diagnostics_bundle_{ts}.json"
            report_path.write_text(report.to_json(), encoding="utf-8")

            md_path = bundle_dir / f"diagnostics_bundle_{ts}.md"
            md_path.write_text(report.to_markdown(), encoding="utf-8")

            result.passed = report_path.exists() and md_path.exists()
            result.details = {
                "json_report": str(report_path),
                "markdown_report": str(md_path),
                "report_success": report.success,
                "phases_count": len(report.phases),
                "dependencies_checked": len(report.dependency_status),
            }
        except Exception as e:
            result.error = f"Bundle export failed: {e}"
            result.details = {"error": str(e)}

        self._results.append(result)
        self._print_result(result)

    def _export_log_collection(self) -> None:
        """Collect and export log files."""
        result = BundleExportResult("log_collection")
        log_dir = _project_root / "data" / "logs"

        try:
            log_dir.mkdir(parents=True, exist_ok=True)

            # Collect existing log files
            log_files = []
            if log_dir.exists():
                for pattern in ["*.json", "*.md", "*.log", "*.txt"]:
                    log_files.extend(log_dir.glob(pattern))

            # Generate a fresh log inventory
            log_inventory = []
            for log_file in log_files:
                log_inventory.append({
                    "name": log_file.name,
                    "size_bytes": log_file.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        log_file.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                })

            # Save inventory
            if self._bundle_dir:
                inventory_path = self._bundle_dir / "log_inventory.json"
                with open(inventory_path, "w", encoding="utf-8") as f:
                    json.dump(log_inventory, f, indent=2, default=str)

            result.passed = True
            result.details = {
                "log_directory": str(log_dir),
                "total_log_files_found": len(log_inventory),
                "log_files": log_inventory[:20],
                "inventory_saved": str(inventory_path) if self._bundle_dir else None,
            }
        except Exception as e:
            result.error = f"Log collection failed: {e}"
            result.details = {"error": str(e)}

        self._results.append(result)
        self._print_result(result)

    def _export_crash_report_bundle(self) -> None:
        """Bundle crash reports if any exist."""
        result = BundleExportResult("crash_report_bundle")
        try:
            # Look for crash-related files
            crash_files = []
            for search_dir in [
                _project_root / "data" / "logs",
                _project_root / "data" / "reports",
            ]:
                if search_dir.exists():
                    for pattern in ["*crash*", "*error*", "*fatal*", "*diagnostic*"]:
                        crash_files.extend(search_dir.glob(pattern))

            # Generate a crash report summary if files exist
            crash_summary = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_crash_files": len(crash_files),
                "crash_files": [
                    {
                        "path": str(f.relative_to(_project_root)),
                        "size_bytes": f.stat().st_size,
                    }
                    for f in crash_files
                ],
                "no_crashes_detected": len(crash_files) == 0,
            }

            if self._bundle_dir:
                crash_path = self._bundle_dir / "crash_report_summary.json"
                with open(crash_path, "w", encoding="utf-8") as f:
                    json.dump(crash_summary, f, indent=2, default=str)

            result.passed = True
            result.details = crash_summary
        except Exception as e:
            result.error = f"Crash report bundling failed: {e}"
            result.details = {"error": str(e)}

        self._results.append(result)
        self._print_result(result)

    def _export_runtime_snapshots(self) -> None:
        """Export runtime state snapshots."""
        result = BundleExportResult("runtime_snapshots")
        try:
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_info": {
                    "platform": sys.platform,
                    "python_version": sys.version,
                    "cwd": os.getcwd(),
                    "pid": os.getpid(),
                },
                "module_state": {
                    "total_modules_loaded": len(sys.modules),
                    "src_modules_loaded": len(
                        [m for m in sys.modules if m.startswith("src.")]
                    ),
                },
                "environment": {
                    key: value for key, value in os.environ.items()
                    if "CORAX" in key.upper() or "PATH" in key.upper()
                },
            }

            if self._bundle_dir:
                snap_path = self._bundle_dir / f"runtime_snapshot_{int(time.time())}.json"
                with open(snap_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, default=str)

            result.passed = True
            result.details = {
                "snapshot_collected": True,
                "snapshot_keys": list(snapshot.keys()),
                "saved_to": str(snap_path) if self._bundle_dir else None,
            }
        except Exception as e:
            result.error = f"Runtime snapshot failed: {e}"
            result.details = {"error": str(e)}

        self._results.append(result)
        self._print_result(result)

    def _verify_bundle_integrity(self) -> None:
        """Verify the integrity of the exported bundle."""
        result = BundleExportResult("bundle_integrity")
        try:
            if not self._bundle_dir or not self._bundle_dir.exists():
                result.passed = False
                result.error = "Bundle directory does not exist"
                result.details = {"bundle_dir": str(self._bundle_dir) if self._bundle_dir else None}
                self._results.append(result)
                self._print_result(result)
                return

            bundle_files = list(self._bundle_dir.glob("*"))
            total_size = sum(f.stat().st_size for f in bundle_files if f.is_file())

            result.passed = len(bundle_files) > 0
            result.details = {
                "bundle_directory": str(self._bundle_dir),
                "total_files_in_bundle": len(bundle_files),
                "total_size_bytes": total_size,
                "files": [str(f.name) for f in bundle_files],
            }
        except Exception as e:
            result.error = f"Bundle integrity check failed: {e}"
            result.details = {"error": str(e)}

        self._results.append(result)
        self._print_result(result)

    def _print_result(self, result: BundleExportResult) -> None:
        """Print a single export result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {result.name}")
        if result.error:
            print(f"         {YELLOW}Error: {result.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the export summary."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Diagnostics Bundle Export Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total exports: {total}")
        print(f"  Passed:        {GREEN}{passed}{RESET}")
        print(f"  Failed:        {RED}{total - passed}{RESET}")
        print(f"  Duration:      {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL BUNDLE EXPORTS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME EXPORTS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete export report."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)

        return {
            "diagnostics_bundle_export_report": {
                "tool": "diagnostics_bundle_exporter.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_exports": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "bundle_directory": str(self._bundle_dir) if self._bundle_dir else None,
                "results": [r.to_dict() for r in self._results],
            }
        }


def main() -> int:
    """Run the diagnostics bundle exporter."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Diagnostics Bundle Exporter"
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clean up source files after bundling"
    )
    args = parser.parse_args()

    exporter = DiagnosticsBundleExporter(clean_after=args.clean)
    report = exporter.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "diagnostics_bundle_export_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["diagnostics_bundle_export_report"]["passed"]
    total = report["diagnostics_bundle_export_report"]["total_exports"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
