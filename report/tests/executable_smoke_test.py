"""
Corax Orchestrator - Executable Smoke Test.

Validates that the built executable can:
1. Start up without crashing
2. Initialize the runtime kernel
3. Run basic commands
4. Handle errors gracefully
5. Generate diagnostics

Run with: python tests/executable_smoke_test.py
Or with the built executable: corax.exe --smoke-test
"""

import sys
import os
import json
import time
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional


# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


class SmokeTestResult:
    """Result of a single smoke test."""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.duration_ms = 0.0
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


class ExecutableSmokeTest:
    """
    Smoke test suite for the Corax Orchestrator executable.

    Tests the executable's startup, initialization, command execution,
    error handling, and diagnostic generation capabilities.
    """

    def __init__(self):
        self._results: List[SmokeTestResult] = []
        self._start_time = time.time()
        self._is_executable = getattr(sys, "frozen", False)

        # Ensure project root is in sys.path for imports
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

    def run_all(self) -> Dict[str, Any]:
        """Run all smoke tests."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator - Executable Smoke Test{RESET}")
        print(f"{'=' * 60}")
        print(f"Mode: {'EXECUTABLE' if self._is_executable else 'SCRIPT'}")
        print(f"Python: {sys.version}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        # Run test groups
        self._test_imports()
        self._test_runtime_kernel()
        self._test_core_modules()
        self._test_deployment_modules()
        self._test_health_modules()
        self._test_error_handling()
        self._test_diagnostics()

        # Print summary
        self._print_summary()

        return self._generate_report()

    def _test_imports(self) -> None:
        """Test that all critical modules can be imported."""
        result = SmokeTestResult("critical_imports")
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

    def _test_runtime_kernel(self) -> None:
        """Test that the runtime kernel initializes correctly."""
        result = SmokeTestResult("runtime_kernel_init")
        start = time.time()

        try:
            from src.runtime.kernel import CoraxRuntimeKernel

            kernel = CoraxRuntimeKernel()
            kernel_result = kernel.start()

            result.passed = kernel_result.success
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "success": kernel_result.success,
                "total_duration_seconds": kernel_result.total_duration_seconds,
                "initialized_components": kernel_result.initialized_components,
                "failed_components": kernel_result.failed_components,
                "error_count": len(kernel_result.errors),
                "warning_count": len(kernel_result.warnings),
            }
            if not kernel_result.success:
                result.error = (
                    f"Kernel failed: {kernel_result.errors[:3]}"
                )
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Kernel init exception: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_core_modules(self) -> None:
        """Test core module initialization."""
        result = SmokeTestResult("core_modules")
        start = time.time()

        try:
            from src.core.logging import get_logger, setup_logging
            from src.core.config import load_config
            from src.core.exceptions import CoraxError

            # Test logging
            setup_logging()
            logger = get_logger("smoke_test")
            logger.info("Smoke test logging initialized")

            # Test config
            config = load_config(None)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "logging_initialized": True,
                "config_loaded": config is not None,
                "exceptions_available": True,
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Core module test failed: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_deployment_modules(self) -> None:
        """Test deployment module initialization."""
        result = SmokeTestResult("deployment_modules")
        start = time.time()

        try:
            from src.deployment.validation import EnvironmentValidator
            from src.deployment.execution.executor import DeploymentExecutor
            from src.deployment.execution.retry_queue import RetryQueue
            from src.deployment.execution.failure_analyzer import (
                FailureAnalyzer,
            )

            # Test instantiation
            validator = EnvironmentValidator()
            executor = DeploymentExecutor()
            retry_queue = RetryQueue()
            failure_analyzer = FailureAnalyzer()

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "validator_created": validator is not None,
                "executor_created": executor is not None,
                "retry_queue_created": retry_queue is not None,
                "failure_analyzer_created": failure_analyzer is not None,
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Deployment module test failed: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_health_modules(self) -> None:
        """Test health/diagnostic module initialization."""
        result = SmokeTestResult("health_modules")
        start = time.time()

        try:
            from src.health.audit import ProjectHealthAudit
            from src.health.packaging import PackagingValidator
            from src.health.diagnostics import StartupDiagnostics
            from src.health.self_setup import SelfSetup

            # Test instantiation
            audit = ProjectHealthAudit()
            packaging = PackagingValidator()
            diagnostics = StartupDiagnostics()
            setup = SelfSetup()

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "audit_created": audit is not None,
                "packaging_created": packaging is not None,
                "diagnostics_created": diagnostics is not None,
                "self_setup_created": setup is not None,
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Health module test failed: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_error_handling(self) -> None:
        """Test error handling and recovery."""
        result = SmokeTestResult("error_handling")
        start = time.time()

        try:
            from src.core.exceptions import CoraxError
            from src.runtime.recovery import StartupRecovery

            # Test CoraxError
            try:
                raise CoraxError("Test error")
            except CoraxError:
                pass  # Expected

            # Test recovery system
            recovery = StartupRecovery()
            recovery_result = recovery.repair_all()

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "corax_error_works": True,
                "recovery_initialized": True,
                "recovery_actions": len(recovery_result.actions),
                "recovery_errors": len(recovery_result.errors),
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Error handling test failed: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _test_diagnostics(self) -> None:
        """Test diagnostic generation."""
        result = SmokeTestResult("diagnostics_generation")
        start = time.time()

        try:
            from src.health.diagnostics import StartupDiagnostics
            from src.runtime.diagnostics import RuntimeDiagnostics

            # Test startup diagnostics
            startup_diag = StartupDiagnostics()
            startup_diag.collect_system_info()
            startup_diag.start_phase("smoke_test")
            startup_diag.end_phase("smoke_test", "success")
            report = startup_diag.finalize(success=True)
            exec_dict = report.to_dict()

            # Test runtime diagnostics
            rt_diag = RuntimeDiagnostics()
            rt_diag.start_phase("smoke_test")
            rt_diag.end_phase("smoke_test", "success")
            rt_report = rt_diag.finalize(success=True)

            result.passed = True
            result.duration_ms = (time.time() - start) * 1000
            result.details = {
                "execution_diagnostics_generated": bool(exec_dict),
                "runtime_diagnostics_generated": rt_report is not None,
                "execution_checks": len(exec_dict.get("checks", [])),
            }
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = f"Diagnostics test failed: {e}"
            result.details = {"traceback": traceback.format_exc()}

        self._results.append(result)
        self._print_result(result)

    def _print_result(self, result: SmokeTestResult) -> None:
        """Print a single test result."""
        status = (
            f"{GREEN}PASS{RESET}"
            if result.passed
            else f"{RED}FAIL{RESET}"
        )
        print(
            f"  [{status}] {result.name} "
            f"({result.duration_ms:.0f}ms)"
        )
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
            print(f"\n{GREEN}{BOLD}  ALL TESTS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME TESTS FAILED{RESET}")
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
                "executable_mode": self._is_executable,
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
    """Run the executable smoke test."""
    test = ExecutableSmokeTest()
    report = test.run_all()

    # Save report
    report_dir = Path("data/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "smoke_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    # Return exit code
    passed = report["smoke_test_report"]["passed"]
    total = report["smoke_test_report"]["total_tests"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
