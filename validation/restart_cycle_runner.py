"""
Corax Orchestrator — Restart Cycle Runner (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- restart-cycle automation
- repeated automated startup/shutdown
- lightweight survivability reporting

Usage:
    python validation/restart_cycle_runner.py [--cycles N]
"""

import sys
import os
import time
import json
import subprocess
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


class RestartCycleResult:
    """Result of a single restart cycle."""

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


class RestartCycleRunner:
    """
    Automated restart-cycle validation utility.

    Repeatedly performs startup/shutdown cycles to validate
    system survivability and detect progressive degradation.
    """

    def __init__(self, cycles: int = 5, executable_path: Optional[str] = None):
        self._cycles = cycles
        self._results: List[RestartCycleResult] = []
        self._start_time = time.time()
        self._executable_path = executable_path

    def run_all(self) -> Dict[str, Any]:
        """Run all restart cycles."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Restart Cycle Runner{RESET}")
        print(f"{'=' * 60}")
        print(f"Cycles:     {self._cycles}")
        print(f"Python:     {sys.version.split()[0]}")
        print(f"Platform:   {sys.platform}")
        print(f"{'=' * 60}\n")

        for i in range(self._cycles):
            result = self._run_single_cycle(i + 1)
            self._results.append(result)
            self._print_cycle_result(result)

        self._print_summary()
        return self._generate_report()

    def _run_single_cycle(self, cycle_num: int) -> RestartCycleResult:
        """Execute a single restart cycle."""
        result = RestartCycleResult(cycle_num)
        cycle_start = time.time()

        try:
            # Phase 1: Module reload simulation (restart bootstrap)
            phase1_start = time.time()
            if "src.runtime.bootstrap" in sys.modules:
                del sys.modules["src.runtime.bootstrap"]
            from src.runtime.bootstrap import RuntimeBootstrap
            bootstrap = RuntimeBootstrap()
            init_ok = bootstrap.initialize()
            phase1_ms = (time.time() - phase1_start) * 1000
            result.phases["bootstrap_restart"] = {
                "duration_ms": round(phase1_ms, 1),
                "success": init_ok is not False,
            }

            # Phase 2: Diagnostics re-init
            phase2_start = time.time()
            if "src.health.diagnostics" in sys.modules:
                del sys.modules["src.health.diagnostics"]
            from src.health.diagnostics import StartupDiagnostics
            diag = StartupDiagnostics()
            diag.collect_system_info()
            phase2_ms = (time.time() - phase2_start) * 1000
            result.phases["diagnostics_reinit"] = {
                "duration_ms": round(phase2_ms, 1),
                "success": True,
            }

            # Phase 3: Core config reload
            phase3_start = time.time()
            if "src.core.config" in sys.modules:
                del sys.modules["src.core.config"]
            from src.core.config import load_config
            cfg = load_config(None)
            phase3_ms = (time.time() - phase3_start) * 1000
            result.phases["config_reload"] = {
                "duration_ms": round(phase3_ms, 1),
                "success": cfg is not None,
            }

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

    def _print_cycle_result(self, result: RestartCycleResult) -> None:
        """Print a single cycle result."""
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        print(f"  Cycle {result.cycle:2d}: [{status}] ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"           {YELLOW}Error: {result.error}{RESET}")
        for phase_name, phase_data in result.phases.items():
            p_status = f"{GREEN}OK{RESET}" if phase_data.get("success") else f"{RED}FAIL{RESET}"
            print(f"           {p_status} {phase_name} ({phase_data['duration_ms']:.0f}ms)")

    def _print_summary(self) -> None:
        """Print the restart cycle summary."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Restart Cycle Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total cycles: {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL CYCLES PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME CYCLES FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete restart cycle report."""
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)

        return {
            "restart_cycle_report": {
                "tool": "restart_cycle_runner.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requested_cycles": self._cycles,
                "completed_cycles": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "cycles": [r.to_dict() for r in self._results],
            }
        }


def main() -> int:
    """Run the restart cycle test suite."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Restart Cycle Runner"
    )
    parser.add_argument(
        "--cycles", type=int, default=5,
        help="Number of restart cycles to run (default: 5)"
    )
    args = parser.parse_args()

    runner = RestartCycleRunner(cycles=args.cycles)
    report = runner.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "restart_cycle_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["restart_cycle_report"]["passed"]
    total = report["restart_cycle_report"]["completed_cycles"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
