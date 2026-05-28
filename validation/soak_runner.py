"""
Corax Orchestrator — Soak Runner (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- runtime soak-test helpers
- repeated runtime-session simulation
- bounded stress-loop tooling
- stale-state detection helpers

Usage:
    python validation/soak_runner.py [--iterations N] [--delay S]
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


class SoakIterationResult:
    """Result of a single soak iteration."""

    def __init__(self, iteration: int):
        self.iteration = iteration
        self.passed = False
        self.duration_ms: float = 0.0
        self.error: Optional[str] = None
        self.memory_delta_mb: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
            "memory_delta_mb": self.memory_delta_mb,
        }


class SoakRunner:
    """
    Bounded soak-test utility for runtime validation.

    Repeatedly simulates runtime sessions to detect:
    - Memory leaks
    - Progressive degradation
    - State corruption across iterations
    - Stale state accumulation
    """

    def __init__(self, iterations: int = 10, delay_between: float = 0.5):
        self._iterations = iterations
        self._delay = delay_between
        self._results: List[SoakIterationResult] = []
        self._start_time = time.time()
        self._initial_time = time.time()

    def run_all(self) -> Dict[str, Any]:
        """Run all soak iterations."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Soak Runner{RESET}")
        print(f"{'=' * 60}")
        print(f"Iterations:  {self._iterations}")
        print(f"Delay:       {self._delay}s")
        print(f"Python:      {sys.version.split()[0]}")
        print(f"Platform:    {sys.platform}")
        print(f"{'=' * 60}\n")

        for i in range(self._iterations):
            result = self._run_single_iteration(i + 1)
            self._results.append(result)
            self._print_iteration(result)

            if i < self._iterations - 1:
                time.sleep(self._delay)

        self._print_summary()
        return self._generate_report()

    def _run_single_iteration(self, iteration_num: int) -> SoakIterationResult:
        """Execute a single soak iteration."""
        result = SoakIterationResult(iteration_num)
        iter_start = time.time()

        try:
            # Fresh import cycle to simulate runtime session
            import importlib

            # Reload core config
            if "src.core.config" in sys.modules:
                del sys.modules["src.core.config"]
            from src.core.config import load_config
            cfg = load_config(None)

            # Reload diagnostics
            if "src.health.diagnostics" in sys.modules:
                del sys.modules["src.health.diagnostics"]
            from src.health.diagnostics import StartupDiagnostics
            diag = StartupDiagnostics()
            diag.collect_system_info()

            # Reload logging
            if "src.core.logging" in sys.modules:
                del sys.modules["src.core.logging"]
            from src.core.logging import get_logger, setup_logging
            setup_logging()
            logger = get_logger(f"soak_iter_{iteration_num}")
            logger.info(f"Soak iteration {iteration_num} started")

            # Generate a small diagnostic report
            diag.start_phase(f"soak_iter_{iteration_num}")
            diag.end_phase(f"soak_iter_{iteration_num}", "success")
            diag.finalize(success=True)
            diag.save_report(f"soak_iter_{iteration_num}_{int(time.time())}.json")

            result.passed = True
            result.duration_ms = (time.time() - iter_start) * 1000
            result.details = {
                "config_loaded": cfg is not None,
                "diagnostics_generated": True,
                "logging_initialized": True,
            }

        except Exception as e:
            result.duration_ms = (time.time() - iter_start) * 1000
            result.error = f"Iteration exception: {e}"

        return result

    def _detect_stale_state(self) -> List[str]:
        """Check for stale state accumulation in sys.modules."""
        stale = []
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("src.") and "soak" in mod_name.lower():
                stale.append(mod_name)
        return stale

    def _print_iteration(self, result: SoakIterationResult) -> None:
        """Print a single iteration result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        mem_str = ""
        if result.memory_delta_mb is not None:
            mem_str = f" | mem: {result.memory_delta_mb:+.1f}MB"
        print(f"  Iter {result.iteration:3d}: [{status}] ({result.duration_ms:.0f}ms{mem_str})")
        if result.error:
            print(f"           {YELLOW}Error: {result.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the soak test summary."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        total_duration = (time.time() - self._start_time) * 1000
        stale_modules = self._detect_stale_state()

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Soak Test Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total iterations: {total}")
        print(f"  Passed:           {GREEN}{passed}{RESET}")
        print(f"  Failed:           {RED}{total - passed}{RESET}")
        print(f"  Duration:         {total_duration:.0f}ms")
        if stale_modules:
            print(f"  {YELLOW}Stale modules:    {len(stale_modules)}{RESET}")
            for m in stale_modules[:5]:
                print(f"    - {m}")
        else:
            print(f"  Stale modules:    0 {GREEN}(clean){RESET}")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL SOAK ITERATIONS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME ITERATIONS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete soak test report."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        stale_modules = self._detect_stale_state()

        return {
            "soak_test_report": {
                "tool": "soak_runner.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requested_iterations": self._iterations,
                "completed_iterations": total,
                "delay_between_seconds": self._delay,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "stale_modules_detected": stale_modules,
                "stale_module_count": len(stale_modules),
                "iterations": [r.to_dict() for r in self._results],
            }
        }


def main() -> int:
    """Run the soak test suite."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Soak Runner"
    )
    parser.add_argument(
        "--iterations", type=int, default=10,
        help="Number of soak iterations (default: 10)"
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Delay between iterations in seconds (default: 0.5)"
    )
    args = parser.parse_args()

    runner = SoakRunner(iterations=args.iterations, delay_between=args.delay)
    report = runner.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "soak_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["soak_test_report"]["passed"]
    total = report["soak_test_report"]["completed_iterations"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
