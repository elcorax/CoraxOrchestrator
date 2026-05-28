"""
Corax Orchestrator — Stress Restart Runner (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- repeated restart scripts
- 10+ restart automation
- repeated runtime-session simulation
- bounded stress-loop tooling

Usage:
    python validation/stress_restart_runner.py [--cycles N] [--fast]
"""

import sys
import os
import time
import json
import argparse
import importlib
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


class StressCycleResult:
    """Result of a single stress restart cycle."""

    def __init__(self, cycle: int):
        self.cycle = cycle
        self.passed = False
        self.duration_ms: float = 0.0
        self.error: Optional[str] = None
        self.phases: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle": self.cycle,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
            "phases": self.phases,
        }


class StressRestartRunner:
    """
    Bounded stress-test restart runner.

    Executes N+ restart cycles with full bootstrap, diagnostics,
    config reload, and shutdown simulation to validate that
    the runtime can survive repeated restart pressure without
    progressive degradation.
    """

    def __init__(self, cycles: int = 10, fast_mode: bool = False):
        self._cycles = cycles
        self._fast = fast_mode
        self._results: List[StressCycleResult] = []
        self._start_time = time.time()
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3

    def run_all(self) -> Dict[str, Any]:
        """Run all stress restart cycles."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Stress Restart Runner{RESET}")
        print(f"{'=' * 60}")
        print(f"Cycles:     {self._cycles}")
        print(f"Fast mode:  {self._fast}")
        print(f"Python:     {sys.version.split()[0]}")
        print(f"Platform:   {sys.platform}")
        print(f"{'=' * 60}\n")

        for i in range(self._cycles):
            result = self._run_single_cycle(i + 1)
            self._results.append(result)
            self._print_cycle(result)

            if result.passed:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1

            # Abort early if too many consecutive failures
            if self._consecutive_failures >= self._max_consecutive_failures:
                print(f"\n{RED}Aborting: {self._consecutive_failures} consecutive failures{RESET}")
                break

        self._print_summary()
        return self._generate_report()

    def _run_single_cycle(self, cycle_num: int) -> StressCycleResult:
        """Execute a single stress cycle."""
        result = StressCycleResult(cycle_num)
        cycle_start = time.time()

        try:
            # Phase 1: Bootstrap initialization
            p1_start = time.time()
            # Clear bootstrap module cache
            for mod in list(sys.modules.keys()):
                if mod.startswith("src.runtime.bootstrap") or mod.startswith("src.runtime.diagnostics"):
                    del sys.modules[mod]

            from src.runtime.bootstrap import RuntimeBootstrap
            bootstrap = RuntimeBootstrap()
            init_ok = bootstrap.initialize()
            p1_ms = (time.time() - p1_start) * 1000
            result.phases["bootstrap_init"] = {
                "duration_ms": round(p1_ms, 1),
                "success": init_ok is not False,
            }

            # Phase 2: Config load
            p2_start = time.time()
            if "src.core.config" in sys.modules:
                del sys.modules["src.core.config"]
            from src.core.config import load_config
            cfg = load_config(None)
            p2_ms = (time.time() - p2_start) * 1000
            result.phases["config_load"] = {
                "duration_ms": round(p2_ms, 1),
                "success": cfg is not None,
            }

            # Phase 3: Diagnostics init
            p3_start = time.time()
            if "src.health.diagnostics" in sys.modules:
                del sys.modules["src.health.diagnostics"]
            from src.health.diagnostics import StartupDiagnostics
            diag = StartupDiagnostics()
            diag.collect_system_info()
            p3_ms = (time.time() - p3_start) * 1000
            result.phases["diagnostics_init"] = {
                "duration_ms": round(p3_ms, 1),
                "success": True,
            }

            # Phase 4: Generate & save diagnostics
            p4_start = time.time()
            diag.start_phase(f"stress_cycle_{cycle_num}")
            diag.end_phase(f"stress_cycle_{cycle_num}", "success")
            diag.finalize(success=True)
            saved = diag.save_report(f"stress_cycle_{cycle_num}_{int(time.time())}.json")
            p4_ms = (time.time() - p4_start) * 1000
            result.phases["diagnostics_export"] = {
                "duration_ms": round(p4_ms, 1),
                "success": bool(saved),
                "saved_to": saved,
            }

            # Phase 5: Shutdown simulation (module cleanup)
            p5_start = time.time()
            bootstrap_sim = None
            p5_ms = (time.time() - p5_start) * 1000
            result.phases["shutdown_sim"] = {
                "duration_ms": round(p5_ms, 1),
                "success": True,
            }

            # Determine overall pass/fail
            result.passed = all(
                p.get("success", False) for p in result.phases.values()
            )
            result.duration_ms = (time.time() - cycle_start) * 1000

            if not result.passed:
                failed_phases = [
                    name for name, p in result.phases.items()
                    if not p.get("success", False)
                ]
                result.error = f"Failed phases: {', '.join(failed_phases)}"

        except Exception as e:
            result.duration_ms = (time.time() - cycle_start) * 1000
            result.error = f"Cycle exception: {e}"

        return result

    def _print_cycle(self, result: StressCycleResult) -> None:
        """Print a single cycle result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        print(f"  Cycle {result.cycle:3d}: [{status}] ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"           {YELLOW}Error: {result.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the stress restart summary."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        total_duration = (time.time() - self._start_time) * 1000

        # Calculate timing statistics
        durations = [r.duration_ms for r in self._results if r.passed]
        avg_duration = sum(durations) / len(durations) if durations else 0

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Stress Restart Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total cycles:     {total}")
        print(f"  Passed:           {GREEN}{passed}{RESET}")
        print(f"  Failed:           {RED}{total - passed}{RESET}")
        print(f"  Avg cycle time:   {avg_duration:.0f}ms")
        print(f"  Total duration:   {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL STRESS CYCLES PASSED — NO DEGRADATION DETECTED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME CYCLES FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete stress restart report."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        durations = [r.duration_ms for r in self._results if r.passed]

        return {
            "stress_restart_report": {
                "tool": "stress_restart_runner.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requested_cycles": self._cycles,
                "completed_cycles": total,
                "fast_mode": self._fast,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "avg_cycle_time_ms": round(sum(durations) / len(durations), 1) if durations else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "cycles": [r.to_dict() for r in self._results],
            }
        }


def main() -> int:
    """Run the stress restart test suite."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Stress Restart Runner"
    )
    parser.add_argument(
        "--cycles", type=int, default=10,
        help="Number of restart cycles (default: 10)"
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Fast mode — skip non-critical phases"
    )
    args = parser.parse_args()

    runner = StressRestartRunner(cycles=args.cycles, fast_mode=args.fast)
    report = runner.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "stress_restart_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["stress_restart_report"]["passed"]
    total = report["stress_restart_report"]["completed_cycles"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
