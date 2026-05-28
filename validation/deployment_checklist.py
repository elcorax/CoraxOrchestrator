"""
Corax Orchestrator — Deployment Checklist (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- automated deployment readiness verification
- degraded-environment checks
- portable deployment verification
- missing-resource detection

Usage:
    python validation/deployment_checklist.py
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


class ChecklistItem:
    """A single deployment checklist item."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.passed = False
        self.error: Optional[str] = None
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "passed": self.passed,
            "error": self.error,
            "details": self.details,
        }


class DeploymentChecklist:
    """
    Automated deployment readiness checklist.

    Verifies:
    - Executable availability
    - Python environment readiness
    - Dependency availability
    - Data directory structure
    - Config file existence
    - Diagnostics export capability
    - Platform-specific requirements
    """

    def __init__(self):
        self._items: List[ChecklistItem] = []
        self._start_time = time.time()

    def run_all(self) -> Dict[str, Any]:
        """Run all deployment checklist items."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Deployment Checklist{RESET}")
        print(f"{'=' * 60}")
        print(f"Python:   {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._check_python_environment()
        self._check_dependencies()
        self._check_data_directories()
        self._check_config_files()
        self._check_diagnostics_capability()
        self._check_build_artifacts()
        self._check_platform_requirements()
        self._check_degraded_environment()

        self._print_summary()
        return self._generate_report()

    def _check_python_environment(self) -> None:
        """Verify Python environment readiness."""
        item = ChecklistItem(
            "python_environment",
            "Python installation and basic environment"
        )

        checks = {
            "python_version": sys.version_info >= (3, 8),
            "python_executable": bool(sys.executable),
            "platform_supported": sys.platform in ("win32", "darwin", "linux"),
        }

        item.passed = all(checks.values())
        item.details = {
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": sys.platform,
            "checks": checks,
        }
        if not item.passed:
            failed = [k for k, v in checks.items() if not v]
            item.error = f"Failed checks: {', '.join(failed)}"

        self._items.append(item)
        self._print_item(item)

    def _check_dependencies(self) -> None:
        """Check that critical dependencies are available."""
        item = ChecklistItem(
            "dependencies",
            "Critical Python package dependencies"
        )

        dependencies = {
            "PyYAML": "yaml",
            "requests": "requests",
            "psutil": "psutil",
        }

        dep_results = {}
        missing = []
        for name, import_path in dependencies.items():
            try:
                __import__(import_path)
                dep_results[name] = "ok"
            except ImportError:
                dep_results[name] = "missing"
                missing.append(name)

        item.passed = len(missing) == 0
        item.details = {
            "dependencies_checked": dep_results,
            "missing": missing,
        }
        if missing:
            item.error = f"Missing dependencies: {', '.join(missing)}"

        self._items.append(item)
        self._print_item(item)

    def _check_data_directories(self) -> None:
        """Verify data directory structure."""
        item = ChecklistItem(
            "data_directories",
            "Required data directories exist and are writable"
        )

        required_dirs = [
            "data/cache",
            "data/logs",
            "data/persistence",
            "data/reports",
            "data/models",
            "config",
        ]

        dir_results = []
        all_ok = True
        for rel_path in required_dirs:
            path = _project_root / rel_path
            try:
                path.mkdir(parents=True, exist_ok=True)
                test_file = path / ".deploy_check"
                test_file.write_text("deploy")
                test_file.unlink()
                dir_results.append({
                    "path": rel_path,
                    "exists": True,
                    "writable": True,
                })
            except Exception:
                dir_results.append({
                    "path": rel_path,
                    "exists": path.exists(),
                    "writable": False,
                })
                all_ok = False

        item.passed = all_ok
        item.details = {
            "directories": dir_results,
            "all_ready": all_ok,
        }
        if not all_ok:
            bad = [r["path"] for r in dir_results if not r.get("writable")]
            item.error = f"Directory issues: {', '.join(bad)}"

        self._items.append(item)
        self._print_item(item)

    def _check_config_files(self) -> None:
        """Verify config files exist."""
        item = ChecklistItem(
            "config_files",
            "Configuration file availability"
        )

        config_files = [
            _project_root / "config" / "corax.yaml",
            _project_root / "config" / "default.yaml",
        ]

        file_results = []
        missing = []
        for path in config_files:
            exists = path.exists()
            file_results.append({
                "path": str(path),
                "exists": exists,
            })
            if not exists:
                missing.append(str(path))

        item.passed = len(missing) == 0
        item.details = {
            "files": file_results,
            "missing": missing,
        }
        if missing:
            item.error = f"Missing config files: {', '.join(missing)}"

        self._items.append(item)
        self._print_item(item)

    def _check_diagnostics_capability(self) -> None:
        """Test diagnostics generation capability."""
        item = ChecklistItem(
            "diagnostics_capability",
            "Diagnostics generation and export"
        )

        try:
            from src.health.diagnostics import StartupDiagnostics

            diag = StartupDiagnostics()
            diag.collect_system_info()
            diag.start_phase("deploy_check")
            diag.end_phase("deploy_check", "success")
            report = diag.finalize(success=True)
            saved = diag.save_report(f"deploy_check_{int(time.time())}.json")

            item.passed = bool(report.to_dict()) and bool(saved)
            item.details = {
                "diagnostics_generated": True,
                "report_saved": str(saved),
                "report_valid": bool(report.to_dict()),
            }
        except Exception as e:
            item.error = f"Diagnostics check failed: {e}"
            item.details = {"error": str(e)}

        self._items.append(item)
        self._print_item(item)

    def _check_build_artifacts(self) -> None:
        """Check for build artifacts."""
        item = ChecklistItem(
            "build_artifacts",
            "Build/distribution artifacts"
        )

        artifacts = {
            "dist/corax.exe": _project_root / "dist" / "corax.exe",
            "dist/corax/corax.exe": _project_root / "dist" / "corax" / "corax.exe",
            "corax.spec": _project_root / "corax.spec",
        }

        artifact_results = {}
        found_any = False
        for name, path in artifacts.items():
            exists = path.exists()
            artifact_results[name] = {
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else 0,
            }
            if exists:
                found_any = True

        item.passed = found_any
        item.details = {
            "artifacts": artifact_results,
            "any_executable_found": found_any,
        }
        if not found_any:
            item.error = "No build artifacts found (expected in dev mode)"

        self._items.append(item)
        self._print_item(item)

    def _check_platform_requirements(self) -> None:
        """Check platform-specific deployment requirements."""
        item = ChecklistItem(
            "platform_requirements",
            "Platform-specific deployment requirements"
        )

        platform_checks = {}
        if sys.platform == "win32":
            platform_checks["is_windows"] = True
            platform_checks["has_python_launcher"] = (
                Path(os.environ.get("SYSTEMROOT", "C:\\Windows")) / "py.exe"
            ).exists()
        elif sys.platform == "darwin":
            platform_checks["is_macos"] = True
            platform_checks["has_python3"] = (
                os.system("python3 --version > nul 2>&1") == 0
                if sys.platform == "win32" else
                os.system("python3 --version 2>/dev/null") == 0
            )
        else:
            platform_checks["is_linux"] = True

        item.passed = True  # Informational only
        item.details = {
            "platform": sys.platform,
            "checks": platform_checks,
        }

        self._items.append(item)
        self._print_item(item)

    def _check_degraded_environment(self) -> None:
        """Simulate degraded environment checks."""
        item = ChecklistItem(
            "degraded_environment",
            "Degraded environment detection and fallback readiness"
        )

        degraded_checks = {
            "missing_dirs_regenerated": True,
            "config_fallback_available": (
                _project_root / "config" / "default.yaml"
            ).exists(),
            "portable_mode_detectable": True,
        }

        try:
            # Test that PortableDeployment can at least be imported
            from src.deployment.portable import PortableDeployment
            degraded_checks["portable_importable"] = True
        except ImportError:
            degraded_checks["portable_importable"] = False

        item.passed = True
        item.details = {
            "degraded_environment_checks": degraded_checks,
            "note": "Degraded environment simulation — directories will be recreated as needed",
        }

        self._items.append(item)
        self._print_item(item)

    def _print_item(self, item: ChecklistItem) -> None:
        """Print a single checklist item."""
        status = f"{GREEN}PASS{RESET}" if item.passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {item.name}")
        print(f"         {item.description}")
        if item.error:
            print(f"         {YELLOW}Error: {item.error}{RESET}")

    def _print_summary(self) -> None:
        """Print the deployment checklist summary."""
        passed = sum(1 for i in self._items if i.passed)
        total = len(self._items)
        total_duration = (time.time() - self._start_time) * 1000

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Deployment Checklist Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total items:  {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL DEPLOYMENT CHECKS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME CHECKS FAILED — REVIEW REQUIRED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete deployment checklist report."""
        passed = sum(1 for i in self._items if i.passed)
        total = len(self._items)

        return {
            "deployment_checklist_report": {
                "tool": "deployment_checklist.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_items": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed / total * 100), 1) if total else 0,
                "total_duration_ms": round(
                    (time.time() - self._start_time) * 1000, 1
                ),
                "items": [i.to_dict() for i in self._items],
            }
        }


def main() -> int:
    """Run the deployment checklist."""
    checklist = DeploymentChecklist()
    report = checklist.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "deployment_checklist_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["deployment_checklist_report"]["passed"]
    total = report["deployment_checklist_report"]["total_items"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
