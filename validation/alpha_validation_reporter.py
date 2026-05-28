"""
Corax Orchestrator — Alpha Validation Reporter (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- survivability report generation
- lightweight validation summaries
- validation reporting reliable

Usage:
    python validation/alpha_validation_reporter.py
"""

import sys
import os
import time
import json
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


class ValidationSummary:
    """Aggregated validation summary for reporting."""

    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.smoke_test_passed = False
        self.restart_test_passed = False
        self.diagnostics_valid = False
        self.executable_found = False
        self.package_valid = False
        self.soak_test_passed = False
        self.stress_test_passed = False
        self.export_valid = False
        self.total_checks = 0
        self.passed_checks = 0
        self.failed_checks = 0
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "smoke_test_passed": self.smoke_test_passed,
            "restart_test_passed": self.restart_test_passed,
            "diagnostics_valid": self.diagnostics_valid,
            "executable_found": self.executable_found,
            "package_valid": self.package_valid,
            "soak_test_passed": self.soak_test_passed,
            "stress_test_passed": self.stress_test_passed,
            "export_valid": self.export_valid,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "overall_status": "PASSED" if self.failed_checks == 0 else "FAILED",
            "details": self.details,
        }


class AlphaValidationReporter:
    """
    Generates comprehensive Internal Alpha validation reports.

    Aggregates results from smoke tests, restart cycles, diagnostics
    validation, executable validation, soak tests, stress tests,
    and diagnostic exports into a unified survivability report.
    """

    def __init__(self):
        self._start_time = time.time()
        self._summary = ValidationSummary()

    def run_all(self) -> Dict[str, Any]:
        """Run all validation reporting operations."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Alpha Validation Reporter{RESET}")
        print(f"{'=' * 60}")
        print(f"Python:   {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._report_smoke_test_results()
        self._report_restart_test_results()
        self._report_diagnostics_validation()
        self._report_executable_status()
        self._report_package_validation()
        self._report_soak_test_results()
        self._report_stress_test_results()
        self._report_export_validation()
        self._generate_survivability_report()
        self._generate_consolidated_summary()

        self._print_summary()
        return self._summary.to_dict()

    def _load_existing_report(self, report_path: Path) -> Optional[Dict[str, Any]]:
        """Load an existing JSON report if available."""
        if report_path.exists():
            try:
                return json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return None
        return None

    def _report_smoke_test_results(self) -> None:
        """Report on smoke test results."""
        report_path = _project_root / "data" / "reports" / "smoke_test_runner_report.json"
        data = self._load_existing_report(report_path)

        if data and "smoke_test_report" in data:
            r = data["smoke_test_report"]
            self._summary.smoke_test_passed = r.get("failed", 1) == 0
            self._summary.details["smoke_test"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "total": r.get("total_tests"),
                "success_rate": r.get("success_rate"),
            }
        else:
            # Run fresh smoke test
            try:
                from validation.smoke_test_runner import SmokeTestRunner
                runner = SmokeTestRunner()
                report = runner.run_all()
                self._summary.smoke_test_passed = report["smoke_test_report"]["failed"] == 0
                self._summary.details["smoke_test"] = report["smoke_test_report"]
            except Exception as e:
                self._summary.details["smoke_test"] = {"error": str(e)}

        print(f"  Smoke test:           {'PASS' if self._summary.smoke_test_passed else 'FAIL'}")

    def _report_restart_test_results(self) -> None:
        """Report on restart cycle test results."""
        report_path = _project_root / "data" / "reports" / "restart_cycle_report.json"
        data = self._load_existing_report(report_path)

        if data and "restart_cycle_report" in data:
            r = data["restart_cycle_report"]
            self._summary.restart_test_passed = r.get("failed", 1) == 0
            self._summary.details["restart_test"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "cycles": r.get("completed_cycles"),
            }
        else:
            try:
                from validation.restart_cycle_runner import RestartCycleRunner
                runner = RestartCycleRunner(cycles=3)
                report = runner.run_all()
                self._summary.restart_test_passed = report["restart_cycle_report"]["failed"] == 0
                self._summary.details["restart_test"] = report["restart_cycle_report"]
            except Exception as e:
                self._summary.details["restart_test"] = {"error": str(e)}

        print(f"  Restart test:         {'PASS' if self._summary.restart_test_passed else 'FAIL'}")

    def _report_diagnostics_validation(self) -> None:
        """Report on diagnostics validation results."""
        report_path = _project_root / "data" / "reports" / "diagnostics_validation_report.json"
        data = self._load_existing_report(report_path)

        if data and "diagnostics_validation_report" in data:
            r = data["diagnostics_validation_report"]
            self._summary.diagnostics_valid = r.get("failed", 1) == 0
            self._summary.details["diagnostics_validation"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "total": r.get("total_checks"),
            }
        else:
            try:
                from validation.diagnostics_validator import DiagnosticsValidator
                validator = DiagnosticsValidator()
                report = validator.run_all()
                self._summary.diagnostics_valid = report["diagnostics_validation_report"]["failed"] == 0
                self._summary.details["diagnostics_validation"] = report["diagnostics_validation_report"]
            except Exception as e:
                self._summary.details["diagnostics_validation"] = {"error": str(e)}

        print(f"  Diagnostics valid:    {'PASS' if self._summary.diagnostics_valid else 'FAIL'}")

    def _report_executable_status(self) -> None:
        """Report on executable status."""
        self._summary.executable_found = any([
            (_project_root / "dist" / "corax" / "corax.exe").exists(),
            (_project_root / "dist" / "corax.exe").exists(),
        ])
        self._summary.details["executable_status"] = {
            "found": self._summary.executable_found,
            "paths_checked": [
                str(_project_root / "dist" / "corax" / "corax.exe"),
                str(_project_root / "dist" / "corax.exe"),
            ],
        }
        print(f"  Executable found:     {'PASS' if self._summary.executable_found else 'SKIP'}")

    def _report_package_validation(self) -> None:
        """Report on package validation results."""
        report_path = _project_root / "data" / "reports" / "package_validation_report.json"
        data = self._load_existing_report(report_path)

        if data and "package_validation_report" in data:
            r = data["package_validation_report"]
            self._summary.package_valid = r.get("failed", 1) == 0
            self._summary.details["package_validation"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "total": r.get("total_checks"),
            }
        else:
            try:
                from validation.package_validation_runner import PackageValidationRunner
                runner = PackageValidationRunner()
                report = runner.run_all()
                self._summary.package_valid = report["package_validation_report"]["failed"] == 0
                self._summary.details["package_validation"] = report["package_validation_report"]
            except Exception as e:
                self._summary.details["package_validation"] = {"error": str(e)}

        print(f"  Package valid:        {'PASS' if self._summary.package_valid else 'FAIL'}")

    def _report_soak_test_results(self) -> None:
        """Report on soak test results."""
        report_path = _project_root / "data" / "reports" / "soak_test_report.json"
        data = self._load_existing_report(report_path)

        if data and "soak_test_report" in data:
            r = data["soak_test_report"]
            self._summary.soak_test_passed = r.get("failed", 1) == 0
            self._summary.details["soak_test"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "iterations": r.get("completed_iterations"),
            }
        else:
            try:
                from validation.soak_runner import SoakRunner
                runner = SoakRunner(iterations=3)
                report = runner.run_all()
                self._summary.soak_test_passed = report["soak_test_report"]["failed"] == 0
                self._summary.details["soak_test"] = report["soak_test_report"]
            except Exception as e:
                self._summary.details["soak_test"] = {"error": str(e)}

        print(f"  Soak test:            {'PASS' if self._summary.soak_test_passed else 'FAIL'}")

    def _report_stress_test_results(self) -> None:
        """Report on stress test results."""
        report_path = _project_root / "data" / "reports" / "stress_restart_report.json"
        data = self._load_existing_report(report_path)

        if data and "stress_restart_report" in data:
            r = data["stress_restart_report"]
            self._summary.stress_test_passed = r.get("failed", 1) == 0
            self._summary.details["stress_test"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "cycles": r.get("completed_cycles"),
            }
        else:
            try:
                from validation.stress_restart_runner import StressRestartRunner
                runner = StressRestartRunner(cycles=5)
                report = runner.run_all()
                self._summary.stress_test_passed = report["stress_restart_report"]["failed"] == 0
                self._summary.details["stress_test"] = report["stress_restart_report"]
            except Exception as e:
                self._summary.details["stress_test"] = {"error": str(e)}

        print(f"  Stress test:          {'PASS' if self._summary.stress_test_passed else 'FAIL'}")

    def _report_export_validation(self) -> None:
        """Report on diagnostics export validation."""
        report_path = _project_root / "data" / "reports" / "diagnostics_bundle_export_report.json"
        data = self._load_existing_report(report_path)

        if data and "diagnostics_bundle_export_report" in data:
            r = data["diagnostics_bundle_export_report"]
            self._summary.export_valid = r.get("failed", 1) == 0
            self._summary.details["export_validation"] = {
                "passed": r.get("passed"),
                "failed": r.get("failed"),
                "total": r.get("total_exports"),
            }
        else:
            try:
                from validation.diagnostics_bundle_exporter import DiagnosticsBundleExporter
                exporter = DiagnosticsBundleExporter()
                report = exporter.run_all()
                self._summary.export_valid = report["diagnostics_bundle_export_report"]["failed"] == 0
                self._summary.details["export_validation"] = report["diagnostics_bundle_export_report"]
            except Exception as e:
                self._summary.details["export_validation"] = {"error": str(e)}

        print(f"  Export valid:         {'PASS' if self._summary.export_valid else 'FAIL'}")

    def _generate_survivability_report(self) -> None:
        """Generate a survivability report based on aggregated data."""
        self._summary.details["survivability_report"] = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "boot_stability": self._summary.smoke_test_passed and self._summary.restart_test_passed,
            "diagnostics_integrity": self._summary.diagnostics_valid,
            "deployment_readiness": self._summary.executable_found or self._summary.package_valid,
            "stress_endurance": self._summary.soak_test_passed and self._summary.stress_test_passed,
            "export_reliability": self._summary.export_valid,
            "overall_assessment": (
                "STABLE"
                if all([
                    self._summary.smoke_test_passed,
                    self._summary.diagnostics_valid,
                    self._summary.soak_test_passed,
                ])
                else "NEEDS_ATTENTION"
            ),
        }

    def _generate_consolidated_summary(self) -> None:
        """Generate the consolidated validation summary."""
        checks = [
            ("smoke_test", self._summary.smoke_test_passed),
            ("restart_test", self._summary.restart_test_passed),
            ("diagnostics_valid", self._summary.diagnostics_valid),
            ("package_valid", self._summary.package_valid),
            ("soak_test", self._summary.soak_test_passed),
            ("stress_test", self._summary.stress_test_passed),
            ("export_valid", self._summary.export_valid),
        ]

        self._summary.total_checks = len(checks)
        self._summary.passed_checks = sum(1 for _, passed in checks if passed)
        self._summary.failed_checks = sum(1 for _, passed in checks if not passed)

    def _print_summary(self) -> None:
        """Print the validation report summary."""
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Alpha Validation Report Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total check categories: {self._summary.total_checks}")
        print(f"  Passed:                 {GREEN}{self._summary.passed_checks}{RESET}")
        print(f"  Failed:                 {RED}{self._summary.failed_checks}{RESET}")
        print(f"  Duration:               {total_duration:.0f}ms")
        print(f"\n  {BOLD}Overall Status: {RESET}", end="")
        if self._summary.failed_checks == 0:
            print(f"{GREEN}{BOLD}PASSED — SYSTEM IS STABLE{RESET}")
        else:
            print(f"{YELLOW}{BOLD}DEGRADED — REVIEW REQUIRED{RESET}")
        print()

    def get_summary(self) -> ValidationSummary:
        """Get the validation summary."""
        return self._summary


def main() -> int:
    """Run the alpha validation reporter."""
    reporter = AlphaValidationReporter()
    report = reporter.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "alpha_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    # Also save a Markdown version
    md_path = report_dir / "alpha_validation_report.md"
    _save_markdown(report, md_path)
    print(f"Markdown saved to: {md_path}")

    return 0 if report.get("failed_checks", 1) == 0 else 1


def _save_markdown(report: Dict[str, Any], path: Path) -> None:
    """Save the report in Markdown format."""
    lines = [
        "# Corax Orchestrator — Internal Alpha Validation Report",
        "",
        f"**Generated:** {report.get('timestamp', 'N/A')}",
        f"**Overall Status:** {'✅ PASSED' if report.get('failed_checks', 1) == 0 else '❌ DEGRADED'}",
        "",
        "---",
        "",
        "## Validation Summary",
        "",
        f"- **Total Categories:** {report.get('total_checks', 0)}",
        f"- **Passed:** {report.get('passed_checks', 0)}",
        f"- **Failed:** {report.get('failed_checks', 0)}",
        "",
        "## Category Results",
        "",
        "| Category | Status |",
        "|----------|--------|",
    ]

    category_map = {
        "smoke_test": "Smoke Test",
        "restart_test": "Restart Cycle Test",
        "diagnostics_valid": "Diagnostics Validation",
        "package_valid": "Package Validation",
        "soak_test": "Soak Test",
        "stress_test": "Stress Test",
        "export_valid": "Export Validation",
    }

    for key, label in category_map.items():
        passed = report.get(key, False)
        icon = "✅" if passed else "❌"
        lines.append(f"| {label} | {icon} |")

    lines.extend([
        "",
        "---",
        "",
        "## Details",
        "",
    ])

    for category, data in report.get("details", {}).items():
        if isinstance(data, dict):
            lines.append(f"### {category}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(data, indent=2, default=str))
            lines.append("```")
            lines.append("")

    lines.extend([
        "---",
        "",
        "*Report generated by Corax Orchestrator Alpha Validation Reporter*",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
