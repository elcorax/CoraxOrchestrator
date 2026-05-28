"""
Corax Orchestrator — Alpha Validation Suite (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- smoke-test orchestration
- restart validation
- executable survivability checks
- diagnostics verification
- bounded soak validation
- clean validation summaries

Usage:
    python validation/alpha_validation_suite.py [--quick]
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


class SuiteStageResult:
    """Result of a single validation suite stage."""

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


class AlphaValidationSuite:
    """
    Comprehensive Internal Alpha validation suite.

    Orchestrates the execution of:
    1. Smoke tests
    2. Restart cycle validation
    3. Diagnostics verification
    4. Soak validation (bounded)
    5. Stress restart validation
    6. Executable validation
    7. Package validation
    8. Diagnostics export validation
    9. Runtime snapshot export
    10. Final aggregated reporting
    """

    def __init__(self, quick_mode: bool = False):
        self._quick = quick_mode
        self._stages: List[SuiteStageResult] = []
        self._start_time = time.time()

    def run_all(self) -> Dict[str, Any]:
        """Run all validation suite stages."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Alpha Validation Suite{RESET}")
        print(f"{'=' * 60}")
        print(f"Mode:      {'QUICK' if self._quick else 'FULL'}")
        print(f"Python:    {sys.version.split()[0]}")
        print(f"Platform:  {sys.platform}")
        print(f"{'=' * 60}\n")

        stages = [
            ("smoke_test", self._run_smoke_test),
            ("diagnostics_validation", self._run_diagnostics_validation),
            ("restart_cycles", self._run_restart_cycles),
            ("soak_validation", self._run_soak_validation),
        ]

        if not self._quick:
            stages.extend([
                ("stress_restart", self._run_stress_restart),
                ("executable_validation", self._run_executable_validation),
                ("package_validation", self._run_package_validation),
                ("diagnostics_export", self._run_diagnostics_export),
                ("runtime_snapshot", self._run_runtime_snapshot),
            ])

        for stage_name, stage_func in stages:
            result = self._execute_stage(stage_name, stage_func)
            self._stages.append(result)
            self._print_stage(result)

        self._print_summary()
        return self._generate_report()

    def _execute_stage(
        self, name: str, func
    ) -> SuiteStageResult:
        """Execute a single validation stage with timing."""
        result = SuiteStageResult(name)
        stage_start = time.time()

        try:
            outcome = func()
            result.passed = outcome
            result.duration_ms = (time.time() - stage_start) * 1000
            result.details = {"completed": True}
        except Exception as e:
            result.duration_ms = (time.time() - stage_start) * 1000
            result.error = f"Stage failed: {e}"
            result.details = {"error": str(e)}

        return result

    def _run_smoke_test(self) -> bool:
        """Run smoke tests."""
        from validation.smoke_test_runner import SmokeTestRunner
        runner = SmokeTestRunner()
        report = runner.run_all()
        return report["smoke_test_report"]["failed"] == 0

    def _run_diagnostics_validation(self) -> bool:
        """Run diagnostics validation."""
        from validation.diagnostics_validator import DiagnosticsValidator
        validator = DiagnosticsValidator()
        report = validator.run_all()
        return report["diagnostics_validation_report"]["failed"] == 0

    def _run_restart_cycles(self) -> bool:
        """Run restart cycle validation."""
        cycles = 3 if self._quick else 5
        from validation.restart_cycle_runner import RestartCycleRunner
        runner = RestartCycleRunner(cycles=cycles)
        report = runner.run_all()
        return report["restart_cycle_report"]["failed"] == 0

    def _run_soak_validation(self) -> bool:
        """Run bounded soak validation."""
        iterations = 3 if self._quick else 10
        from validation.soak_runner import SoakRunner
        runner = SoakRunner(iterations=iterations)
        report = runner.run_all()
        return report["soak_test_report"]["failed"] == 0

    def _run_stress_restart(self) -> bool:
        """Run stress restart validation."""
        from validation.stress_restart_runner import StressRestartRunner
        runner = StressRestartRunner(cycles=10)
        report = runner.run_all()
        return report["stress_restart_report"]["failed"] == 0

    def _run_executable_validation(self) -> bool:
        """Run executable validation."""
        from validation.executable_validator import ExecutableValidator
        validator = ExecutableValidator()
        report = validator.run_all()
        return report["executable_validation_report"]["failed"] == 0

    def _run_package_validation(self) -> bool:
        """Run package validation."""
        from validation.package_validation_runner import PackageValidationRunner
        runner = PackageValidationRunner()
        report = runner.run_all()
        return report["package_validation_report"]["failed"] == 0

    def _run_diagnostics_export(self) -> bool:
        """Run diagnostics export validation."""
        from validation.diagnostics_bundle_exporter import DiagnosticsBundleExporter
        exporter = DiagnosticsBundleExporter()
        report = exporter.run_all()
        return report["diagnostics_bundle_export_report"]["failed"] == 0

    def _run_runtime_snapshot(self) -> bool:
        """Run runtime snapshot export."""
        from validation.runtime_snapshot_exporter import RuntimeSnapshotExporter
        exporter = RuntimeSnapshotExporter()
        report = exporter.run_all()
        return report["runtime_snapshot_export_report"]["failed"] == 0

    def _print_stage(self, result: SuiteStageResult) -> None:
        """Print a single stage result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {result.name} ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"         {YELLOW}Error: {result.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the suite summary."""
        passed = sum(1 for s in self._stages if s.passed)
        total = len(self._stages)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Alpha Validation Suite Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total stages: {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL STAGES PASSED — SYSTEM VALIDATED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME STAGES FAILED — REVIEW REQUIRED{RESET}")
            for s in self._stages:
                if not s.passed:
                    print(f"    - {s.name}: {s.error}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete suite report."""
        passed = sum(1 for s in self._stages if s.passed)
        total = len(self._stages)

        return {
            "alpha_validation_suite_report": {
                "tool": "alpha_validation_suite.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "quick" if self._quick else "full",
                "total_stages": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "stages": [s.to_dict() for s in self._stages],
            }
        }


def main() -> int:
    """Run the alpha validation suite."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Alpha Validation Suite"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick mode — run essential stages only"
    )
    args = parser.parse_args()

    suite = AlphaValidationSuite(quick_mode=args.quick)
    report = suite.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "alpha_validation_suite_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Suite report saved to: {report_path}")

    passed = report["alpha_validation_suite_report"]["passed"]
    total = report["alpha_validation_suite_report"]["total_stages"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
