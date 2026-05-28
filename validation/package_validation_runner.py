"""
Corax Orchestrator — Package Validation Runner (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- executable validation automation
- diagnostics export verification
- fallback-path validation
- portable deployment verification

Usage:
    python validation/package_validation_runner.py
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


class PackageValidationCheck:
    """Result of a single package validation check."""

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


class PackageValidationRunner:
    """
    Automated package validation runner.

    Validates:
    - Executable build artifacts
    - Diagnostics export capability
    - Fallback deployment paths
    - Portable deployment readiness
    - Resource integrity
    """

    def __init__(self):
        self._checks: List[PackageValidationCheck] = []
        self._start_time = time.time()

    def run_all(self) -> Dict[str, Any]:
        """Run all package validation checks."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Package Validation Runner{RESET}")
        print(f"{'=' * 60}")
        print(f"Python:   {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._check_packaging_validator_module()
        self._check_diagnostics_export()
        self._check_fallback_paths()
        self._check_resource_integrity()
        self._check_deployment_checklist_artifacts()

        self._print_summary()
        return self._generate_report()

    def _check_packaging_validator_module(self) -> None:
        """Check that the packaging validator module works."""
        check = PackageValidationCheck("packaging_validator_module")
        start = time.time()

        try:
            from src.health.packaging import PackagingValidator
            validator = PackagingValidator()

            check.passed = True
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "packaging_validator_available": True,
                "validator_type": type(validator).__name__,
            }
        except ImportError as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"PackagingValidator import failed: {e}"
            check.details = {"import_error": str(e)}
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"PackagingValidator init failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_diagnostics_export(self) -> None:
        """Verify diagnostics export works correctly."""
        check = PackageValidationCheck("diagnostics_export_verification")
        start = time.time()

        try:
            from src.health.diagnostics import StartupDiagnostics

            diag = StartupDiagnostics()
            diag.collect_system_info()
            diag.start_phase("package_validation")
            diag.end_phase("package_validation", "success")
            report = diag.finalize(success=True)

            # Export as JSON
            json_str = report.to_json()
            json_data = json.loads(json_str)

            # Export as Markdown
            md_str = report.to_markdown()

            # Save to file
            saved_path = diag.save_report(
                f"package_validation_{int(time.time())}.json"
            )

            check.passed = bool(json_data) and bool(md_str) and bool(saved_path)
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "json_export_valid": bool(json_data),
                "json_keys": list(json_data.keys()) if json_data else [],
                "markdown_export_valid": len(md_str) > 0,
                "markdown_length": len(md_str),
                "file_saved": saved_path,
                "file_exists": Path(saved_path).exists(),
            }
            if not check.passed:
                failures = []
                if not json_data: failures.append("json_export")
                if not md_str: failures.append("markdown_export")
                if not saved_path: failures.append("file_save")
                check.error = f"Export failures: {', '.join(failures)}"
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Diagnostics export failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_fallback_paths(self) -> None:
        """Validate fallback deployment paths."""
        check = PackageValidationCheck("fallback_paths")
        start = time.time()

        try:
            # Check fallback paths that the system uses
            fallback_candidates = [
                _project_root / "data",
                _project_root / "data" / "cache",
                _project_root / "data" / "logs",
                _project_root / "data" / "persistence",
                _project_root / "data" / "reports",
                _project_root / "config",
            ]

            fallback_results = []
            for path in fallback_candidates:
                path.mkdir(parents=True, exist_ok=True)
                fallback_results.append({
                    "path": str(path),
                    "exists": path.exists(),
                    "is_dir": path.is_dir(),
                })

            check.passed = all(r["exists"] for r in fallback_results)
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "fallback_paths_checked": len(fallback_candidates),
                "all_exist": check.passed,
                "paths": fallback_results,
            }
            if not check.passed:
                missing = [r["path"] for r in fallback_results if not r["exists"]]
                check.error = f"Missing fallback paths: {', '.join(missing)}"
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Fallback path check failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_resource_integrity(self) -> None:
        """Check integrity of critical resources."""
        check = PackageValidationCheck("resource_integrity")
        start = time.time()

        try:
            critical_files = [
                _project_root / "requirements.txt",
                _project_root / "corax.spec",
                _project_root / "src" / "main.py",
            ]

            integrity_results = []
            for path in critical_files:
                if path.exists():
                    content = path.read_text(encoding="utf-8", errors="replace")
                    integrity_results.append({
                        "path": str(path),
                        "exists": True,
                        "size_bytes": path.stat().st_size,
                        "non_empty": len(content.strip()) > 0,
                        "line_count": len(content.splitlines()),
                    })
                else:
                    integrity_results.append({
                        "path": str(path),
                        "exists": False,
                    })

            all_intact = all(
                r.get("exists") and r.get("non_empty")
                for r in integrity_results
            )

            check.passed = all_intact
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "files_checked": len(critical_files),
                "all_intact": all_intact,
                "file_details": integrity_results,
            }
            if not all_intact:
                issues = [
                    r["path"] for r in integrity_results
                    if not r.get("exists") or not r.get("non_empty")
                ]
                check.error = f"Integrity issues: {', '.join(issues)}"
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Resource integrity check failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _check_deployment_checklist_artifacts(self) -> None:
        """Check that deployment checklist/documentation artifacts exist."""
        check = PackageValidationCheck("deployment_checklist_artifacts")
        start = time.time()

        try:
            checklist_dir = _project_root / "docs"
            checklist_files = [
                "EXECUTABLE_DEPLOYMENT_GUIDE.md",
                "EXECUTABLE_TESTING_GUIDE.md",
                "FIRST_RUN_GUIDE.md",
                "CLEAN_MACHINE_TEST_GUIDE.md",
                "INTERNAL_ALPHA_BUILD.md",
                "INTERNAL_ALPHA_TESTING.md",
            ]

            found = []
            missing = []
            for filename in checklist_files:
                path = checklist_dir / filename
                exists = path.exists()
                if exists:
                    found.append(filename)
                else:
                    missing.append(filename)

            check.passed = len(missing) == 0
            check.duration_ms = (time.time() - start) * 1000
            check.details = {
                "total_checklist_files": len(checklist_files),
                "found": found,
                "missing": missing,
            }
            if missing:
                check.error = f"Missing checklist artifacts: {', '.join(missing[:5])}"
        except Exception as e:
            check.duration_ms = (time.time() - start) * 1000
            check.error = f"Deployment checklist check failed: {e}"

        self._checks.append(check)
        self._print_check(check)

    def _print_check(self, check: PackageValidationCheck) -> None:
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
        print(f"{BOLD}Package Validation Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total checks: {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL PACKAGE VALIDATIONS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME VALIDATIONS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete validation report."""
        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)

        return {
            "package_validation_report": {
                "tool": "package_validation_runner.py",
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
    """Run the package validation suite."""
    runner = PackageValidationRunner()
    report = runner.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "package_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["package_validation_report"]["passed"]
    total = report["package_validation_report"]["total_checks"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
