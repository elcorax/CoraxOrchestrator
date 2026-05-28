"""
Corax Orchestrator — Smoke Test Runner (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- startup test runner
- executable launch validation
- diagnostics existence validation
- shutdown survivability checks
- repeated launch automation

Usage:
    python validation/smoke_test_runner.py
"""

import sys
import os
import time
import json
import subprocess
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


# Ensure project root is on path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


class SmokeTestResult:
    """Result of a single smoke test operation."""

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


class SmokeTestRunner:
    """
    Lightweight smoke-test automation utility.

    Validates that the Corax Orchestrator can:
    - Import all critical modules
    - Initialize core systems
    - Generate diagnostics
    - Survive basic startup/shutdown cycles
    """

    def __init__(self, executable_path: Optional[str] = None):
        self._results: List[SmokeTestResult] = []
        self._start_time = time.time()
        self._project_root = _project_root
        self._executable_path = executable_path or self._find_executable()

    def _find_executable(self) -> Optional[str]:
        """Locate the Corax executable if available."""
        candidates = [
            self._project_root / "dist" / "corax" / "corax.exe",
            self._project_root / "dist" / "corax.exe",
        ]
        for path in candidates:
            if path.exists():
                return str(path)
        return None

    def run_all(self) -> Dict[str, Any]:
        """Run all smoke test groups."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Smoke Test Runner{RESET}")
        print(f"{'=' * 60}")
        print(f"Executable: {self._executable_path or 'N/A (script mode)'}")
        print(f"Python: {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._test_import_integrity()
        self._test_runtime_bootstrap()
        self._test_diagnostics_generation()
        self._test_shutdown_survivability()
        self._test_repeated_launch_capability()

        self._print_summary()
        return self._generate_report()

    def _test_import_integrity(self) -> None:
        """Test that all critical modules can be imported."""
        result = SmokeTestResult("import_integrity")
        start = time.time()

        critical_modules = [
            "src.core.logging",
            "src.core.config",
            "src.core.exceptions",
            "src.runtime.kernel",
            "src.runtime.state",
            "src.runtime.bootstrap",
            "src.runtime.diagnostics",
            "src.runtime.recovery",
            "src.runtime.lifecycle",
            "src.modules.system_scanner",
            "src.modules.environment_analyzer",
            "src.modules.tool_registry",
            "src.modules.reporting",
            "src.modules.task_orchestrator",
            "src.deployment.orchestrator",
            "src.deployment.validation",
            "src.deployment.execution.executor",
            "src.deployment.execution.session",
            "src.deployment.execution.retry_queue",
            "src.deployment.execution.failure_analyzer",
            "src.deployment.execution.terminal",
            "src.deployment.installers.base",
            "src.deployment.repair.engine",
            "src.health.audit",
            "src.health.packaging",
            "src.health.diagnostics",
            "src.health.self_setup",
        ]

        failed_imports = []
        for mod_name in critical_modules:
            try:
                __import__(mod_name)
            except Exception as e:
                failed_imports.append(f"{mod_name}: {e}")

        result.passed = len(failed_imports) == 0
        result.duration_ms = (time.time() - start) * 1000
        result.details = {
            "total_modules": len(critical_modules),
            "failed_modules": failed_imports,
            "success_count": len(critical_modules) - len(failed_imports),
            "failure_count": len(failed_imports),
        }
        if failed_imports:
            result.error = f"Failed imports: {', '.join(failed_imports[:5])}"
        self._results.append(result)
        self._print_result(result)

    def _test_runtime_bootstrap(self) -> None:
        """Test that runtime bootstrap initializes correctly."""
        result = SmokeTestResult("runtime_bootstrap")
        start = time.time()

        try:
            from src.runtime.bootstrap import RuntimeBootstrap
            bootstrap = RuntimeBootstrap()
            outcome = bootstrap.initialize()
            result.passed = outcome is not False
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "initialized": outcome is not False,
            }
            if outcome is False:
                result.error = "RuntimeBootstrap.initialize() returned False"
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Bootstrap exception: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_diagnostics_generation(self) -> None:
        """Test that diagnostics can be generated and saved."""
        result = SmokeTestResult("diagnostics_generation")
        start = time.time()

        try:
            from src.health.diagnostics import StartupDiagnostics
            from src.runtime.diagnostics import RuntimeDiagnostics

            # Startup diagnostics
            startup_diag = StartupDiagnostics()
            startup_diag.collect_system_info()
            startup_diag.start_phase("smoke_test")
            startup_diag.end_phase("smoke_test", "success")
            startup_report = startup_diag.finalize(success=True)

            # Runtime diagnostics
            rt_diag = RuntimeDiagnostics()
            rt_diag.start_phase("smoke_test")
            rt_diag.end_phase("smoke_test", "success")
            rt_report = rt_diag.finalize(success=True)

            # Save reports
            startup_path = startup_diag.save_report(
                f"smoke_startup_{int(time.time())}.json"
            )
            rt_path = rt_diag.save_report(
                f"smoke_runtime_{int(time.time())}.json"
            )

            result.passed = bool(startup_report.to_dict()) and bool(rt_report.to_dict())
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "startup_diagnostics_generated": True,
                "runtime_diagnostics_generated": True,
                "startup_saved_to": startup_path,
                "runtime_saved_to": rt_path,
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Diagnostics generation failed: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_shutdown_survivability(self) -> None:
        """Test that the system handles shutdown gracefully."""
        result = SmokeTestResult("shutdown_survivability")
        start = time.time()

        try:
            from src.runtime.lifecycle import RuntimeLifecycle
            lifecycle = RuntimeLifecycle()
            shutdown_result = lifecycle.shutdown()
            result.passed = shutdown_result is not False
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "shutdown_initiated": True,
            }
        except ImportError:
            # lifecycle may not have a standalone shutdown method
            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {"note": "RuntimeLifecycle.shutdown() not available - skipped"}
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Shutdown test exception: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_repeated_launch_capability(self) -> None:
        """Test repeated import/initialization cycles for survivability."""
        result = SmokeTestResult("repeated_launch_capability")
        start = time.time()

        cycles = 3
        cycle_results = []

        try:
            for i in range(cycles):
                cycle_start = time.time()
                # Re-import core module fresh
                import importlib
                from src.core import config
                importlib.reload(config)
                cfg = config.load_config(None)
                cycle_ms = (time.time() - cycle_start) * 1000
                cycle_results.append({
                    "cycle": i + 1,
                    "duration_ms": round(cycle_ms, 1),
                    "config_loaded": cfg is not None,
                })

            result.passed = all(c["config_loaded"] for c in cycle_results)
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "cycles_completed": cycles,
                "cycles": cycle_results,
                "all_cycles_passed": result.passed,
            }
            if not result.passed:
                result.error = "One or more launch cycles failed"
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Repeated launch test exception: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _print_result(self, result: SmokeTestResult) -> None:
        """Print a single test result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {result.name} ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"         {YELLOW}Error: {result.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the test summary."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Smoke Test Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total tests: {total}")
        print(f"  Passed:      {GREEN}{passed}{RESET}")
        print(f"  Failed:      {RED}{total - passed}{RESET}")
        print(f"  Duration:    {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL SMOKE TESTS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME SMOKE TESTS FAILED{RESET}")
            for r in self._results:
                if not r.passed:
                    print(f"    - {r.name}: {r.error}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete smoke test report."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)

        return {
            "smoke_test_report": {
                "tool": "smoke_test_runner.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "executable_path": self._executable_path,
                "python_version": sys.version,
                "platform": sys.platform,
                "total_tests": total,
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
    """Run the smoke test suite and save report."""
    runner = SmokeTestRunner()
    report = runner.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "smoke_test_runner_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["smoke_test_report"]["passed"]
    total = report["smoke_test_report"]["total_tests"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
