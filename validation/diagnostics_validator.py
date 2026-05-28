"""
Corax Orchestrator — Diagnostics Validator (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- diagnostics existence validation
- diagnostics generation verification
- lightweight survivability reporting

Usage:
    python validation/diagnostics_validator.py
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


class ValidationCheck:
    """Result of a single diagnostics validation check."""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.details: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "error": self.error,
        }


class DiagnosticsValidator:
    """
    Validates diagnostics generation, export, and reporting capabilities.

    Checks that:
    - Runtime diagnostics can generate reports
    - Startup diagnostics can generate reports
    - Reports can be exported as JSON, Markdown
    - Diagnostics directory exists and is writable
    - Previous diagnostic reports are readable
    """

    def __init__(self):
        self._checks: List[ValidationCheck] = []
        self._start_time = time.time()
        self._project_root = _project_root

    def run_all(self) -> Dict[str, Any]:
        """Run all diagnostics validation checks."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Diagnostics Validator{RESET}")
        print(f"{'=' * 60}")
        print(f"Python:   {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._check_diagnostics_existence()
        self._check_diagnostics_generation()
        self._check_diagnostics_export()
        self._check_log_directory()
        self._check_report_directory()
        self._check_diagnostics_report_format()

        self._print_summary()
        return self._generate_report()

    def _check_diagnostics_existence(self) -> None:
        """Check that diagnostic modules exist and can be imported."""
        check = ValidationCheck("diagnostics_module_existence")
        try:
            from src.health.diagnostics import StartupDiagnostics, DiagnosticReport
            from src.runtime.diagnostics import RuntimeDiagnostics, RuntimeDiagnosticReport

            check.passed = True
            check.details = {
                "startup_diagnostics": True,
                "runtime_diagnostics": True,
                "diagnostic_report_class": True,
                "runtime_diagnostic_report_class": True,
            }
        except ImportError as e:
            check.error = f"Diagnostics import failed: {e}"
            check.details = {"import_error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _check_diagnostics_generation(self) -> None:
        """Test that diagnostics can be generated."""
        check = ValidationCheck("diagnostics_generation")
        try:
            from src.health.diagnostics import StartupDiagnostics

            diag = StartupDiagnostics()
            diag.collect_system_info()
            diag.start_phase("validation_test")
            diag.end_phase("validation_test", "success")
            report = diag.finalize(success=True)
            report_dict = report.to_dict()

            required_keys = ["timestamp", "success", "system_info", "errors", "performance"]
            missing_keys = [k for k in required_keys if k not in report_dict]

            check.passed = len(missing_keys) == 0
            check.details = {
                "report_generated": True,
                "success_status": report_dict.get("success"),
                "system_info_collected": bool(report_dict.get("system_info")),
                "errors_empty": len(report_dict.get("errors", [])) == 0,
                "missing_keys": missing_keys,
            }
            if missing_keys:
                check.error = f"Missing report keys: {missing_keys}"
        except Exception as e:
            check.error = f"Generation failed: {e}"
            check.details = {"error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _check_diagnostics_export(self) -> None:
        """Test diagnostic report export to JSON and Markdown."""
        check = ValidationCheck("diagnostics_export")
        try:
            from src.health.diagnostics import StartupDiagnostics

            diag = StartupDiagnostics()
            diag.collect_system_info()
            diag.start_phase("export_test")
            diag.end_phase("export_test", "success")
            report = diag.finalize(success=True)

            # Export to JSON string
            json_str = report.to_json()
            json_parsed = json.loads(json_str)

            # Export to Markdown
            md_str = report.to_markdown()

            # Save to file
            saved_path = diag.save_report(f"validation_export_{int(time.time())}.json")

            check.passed = bool(json_parsed) and bool(md_str) and bool(saved_path)
            check.details = {
                "json_export_valid": bool(json_parsed),
                "json_keys": list(json_parsed.keys()),
                "markdown_export_valid": len(md_str) > 0,
                "markdown_length": len(md_str),
                "saved_to": saved_path,
                "file_exists": Path(saved_path).exists(),
            }
        except Exception as e:
            check.error = f"Export failed: {e}"
            check.details = {"error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _check_log_directory(self) -> None:
        """Check that the log directory exists and is writable."""
        check = ValidationCheck("log_directory")
        log_dir = self._project_root / "data" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            test_file = log_dir / ".write_test"
            test_file.write_text("write test")
            test_file.unlink()

            check.passed = True
            check.details = {
                "path": str(log_dir),
                "exists": log_dir.exists(),
                "writable": True,
            }
        except Exception as e:
            check.error = f"Log directory check failed: {e}"
            check.details = {"path": str(log_dir), "error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _check_report_directory(self) -> None:
        """Check that the report directory exists and is writable."""
        check = ValidationCheck("report_directory")
        report_dir = self._project_root / "data" / "reports"
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
            test_file = report_dir / ".write_test"
            test_file.write_text("write test")
            test_file.unlink()

            # Check for existing reports
            existing_reports = list(report_dir.glob("*.json"))
            existing_reports.extend(list(report_dir.glob("*.md")))

            check.passed = True
            check.details = {
                "path": str(report_dir),
                "exists": report_dir.exists(),
                "writable": True,
                "existing_reports_count": len(existing_reports),
                "existing_reports": [str(r.name) for r in existing_reports[:10]],
            }
        except Exception as e:
            check.error = f"Report directory check failed: {e}"
            check.details = {"path": str(report_dir), "error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _check_diagnostics_report_format(self) -> None:
        """Validate the structure and format of a generated report."""
        check = ValidationCheck("report_format_validation")
        try:
            from src.health.diagnostics import StartupDiagnostics

            diag = StartupDiagnostics()
            diag.collect_system_info()
            diag.start_phase("format_test")
            diag.end_phase("format_test", "success")
            report = diag.finalize(success=True)
            d = report.to_dict()

            # Validate structure
            format_checks = {
                "has_timestamp": isinstance(d.get("timestamp"), str),
                "has_success_bool": isinstance(d.get("success"), bool),
                "has_system_info": isinstance(d.get("system_info"), dict),
                "has_errors_list": isinstance(d.get("errors"), list),
                "has_warnings_list": isinstance(d.get("warnings"), list),
                "has_performance": isinstance(d.get("performance"), dict),
                "has_dependency_status": isinstance(d.get("dependency_status"), dict),
                "system_info_has_platform": "platform" in d.get("system_info", {}),
                "system_info_has_python": "python_version" in d.get("system_info", {}),
            }

            check.passed = all(format_checks.values())
            check.details = {
                "format_checks": format_checks,
                "failed_checks": [
                    k for k, v in format_checks.items() if not v
                ],
            }
            if not check.passed:
                failed = [k for k, v in format_checks.items() if not v]
                check.error = f"Format validation failed: {', '.join(failed)}"
        except Exception as e:
            check.error = f"Format validation failed: {e}"
            check.details = {"error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _print_check(self, check: ValidationCheck) -> None:
        """Print a single validation check result."""
        status = f"{GREEN}PASS{RESET}" if check.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {check.name}")
        if check.error:
            print(f"         {YELLOW}Error: {check.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the validation summary."""
        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Diagnostics Validation Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total checks: {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL VALIDATION CHECKS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME CHECKS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete validation report."""
        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)

        return {
            "diagnostics_validation_report": {
                "tool": "diagnostics_validator.py",
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
    """Run the diagnostics validator."""
    validator = DiagnosticsValidator()
    report = validator.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "diagnostics_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["diagnostics_validation_report"]["passed"]
    total = report["diagnostics_validation_report"]["total_checks"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
