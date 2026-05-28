"""
Corax Orchestrator — Executable Validator (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- executable existence validation
- packaged resource checks
- writable-directory checks
- portable deployment verification
- missing-resource detection

Usage:
    python validation/executable_validator.py
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


class ExecutableValidationResult:
    """Result of a single executable validation check."""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: Optional[str] = None
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "error": self.error,
            "details": self.details,
        }


class ExecutableValidator:
    """
    Validates executable build artifacts and deployment packaging.

    Checks:
    - Built executable exists (dist/corax.exe, dist/corax/corax.exe)
    - Packaged resources are present
    - Data directories are writable
    - Portable deployment paths are valid
    - Missing critical resources are detected
    """

    def __init__(self):
        self._checks: List[ExecutableValidationResult] = []
        self._start_time = time.time()

    def run_all(self) -> Dict[str, Any]:
        """Run all executable validation checks."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Executable Validator{RESET}")
        print(f"{'=' * 60}")
        print(f"Python:   {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")
        print(f"{'=' * 60}\n")

        self._check_executable_exists()
        self._check_packaged_resources()
        self._check_writable_directories()
        self._check_portable_deployment()
        self._check_missing_resources()
        self._check_dist_directory()

        self._print_summary()
        return self._generate_report()

    def _check_executable_exists(self) -> None:
        """Check that the built executable exists."""
        check = ExecutableValidationResult("executable_exists")
        candidates = [
            _project_root / "dist" / "corax" / "corax.exe",
            _project_root / "dist" / "corax.exe",
        ]

        found = []
        for path in candidates:
            found.append({
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            })

        any_found = any(f["exists"] for f in found)
        check.passed = any_found
        check.details = {
            "candidates_checked": len(candidates),
            "found_in": [f["path"] for f in found if f["exists"]],
            "details": found,
        }
        if not any_found:
            check.error = "No built executable found in dist/ directory"

        self._checks.append(check)
        self._print_check(check)

    def _check_packaged_resources(self) -> None:
        """Check that packaged resources are present."""
        check = ExecutableValidationResult("packaged_resources")
        required_resources = [
            ("config/corax.yaml", "Corax config"),
            ("config/default.yaml", "Default config"),
            ("data/cache/", "Cache directory"),
            ("data/logs/", "Logs directory"),
            ("data/persistence/", "Persistence directory"),
            ("data/reports/", "Reports directory"),
        ]

        results = []
        missing = []
        for rel_path, description in required_resources:
            full_path = _project_root / rel_path
            exists = full_path.exists()
            results.append({
                "path": rel_path,
                "description": description,
                "exists": exists,
            })
            if not exists:
                missing.append(rel_path)

        check.passed = len(missing) == 0
        check.details = {
            "total_resources": len(required_resources),
            "present": len(required_resources) - len(missing),
            "missing": missing,
            "resource_details": results,
        }
        if missing:
            check.error = f"Missing resources: {', '.join(missing[:5])}"

        self._checks.append(check)
        self._print_check(check)

    def _check_writable_directories(self) -> None:
        """Check that data directories are writable."""
        check = ExecutableValidationResult("writable_directories")
        writable_dirs = [
            _project_root / "data" / "cache",
            _project_root / "data" / "logs",
            _project_root / "data" / "persistence",
            _project_root / "data" / "reports",
            _project_root / "data" / "models",
        ]

        results = []
        all_writable = True
        for path in writable_dirs:
            try:
                path.mkdir(parents=True, exist_ok=True)
                test_file = path / ".write_test"
                test_file.write_text("permission test")
                test_file.unlink()
                writable = True
            except (OSError, PermissionError):
                writable = False
                all_writable = False

            results.append({
                "path": str(path),
                "exists": path.exists(),
                "writable": writable,
            })

        check.passed = all_writable
        check.details = {
            "directories_checked": len(writable_dirs),
            "all_writable": all_writable,
            "directory_details": results,
        }
        if not all_writable:
            unwritable = [r["path"] for r in results if not r["writable"]]
            check.error = f"Unwritable directories: {', '.join(unwritable[:3])}"

        self._checks.append(check)
        self._print_check(check)

    def _check_portable_deployment(self) -> None:
        """Check portable deployment paths are valid."""
        check = ExecutableValidationResult("portable_deployment")
        try:
            from src.deployment.portable import PortableDeployment
            portable = PortableDeployment()

            check.passed = True
            check.details = {
                "portable_class_available": True,
                "is_portable": portable.is_portable if hasattr(portable, 'is_portable') else "unknown",
                "root_path": str(portable.root_path) if hasattr(portable, 'root_path') else "unknown",
            }
        except ImportError as e:
            check.passed = True  # Non-critical if portable not available
            check.details = {
                "portable_class_available": False,
                "note": "PortableDeployment not available — non-critical",
            }
        except Exception as e:
            check.error = f"Portable deployment check failed: {e}"
            check.details = {"error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _check_missing_resources(self) -> None:
        """Detect missing critical resources."""
        check = ExecutableValidationResult("missing_resource_detection")
        critical_paths = [
            _project_root / "src" / "main.py",
            _project_root / "src" / "runtime" / "kernel.py",
            _project_root / "src" / "runtime" / "bootstrap.py",
            _project_root / "src" / "runtime" / "diagnostics.py",
            _project_root / "src" / "health" / "diagnostics.py",
            _project_root / "src" / "deployment" / "portable.py",
            _project_root / "corax.spec",
            _project_root / "requirements.txt",
        ]

        missing = []
        found = []
        for path in critical_paths:
            exists = path.exists()
            if exists:
                found.append(str(path))
            else:
                missing.append(str(path))

        check.passed = len(missing) == 0
        check.details = {
            "total_critical": len(critical_paths),
            "found": len(found),
            "missing": missing,
            "critical_paths_checked": found[:10],
        }
        if missing:
            check.error = f"Missing critical resources: {', '.join(missing[:5])}"

        self._checks.append(check)
        self._print_check(check)

    def _check_dist_directory(self) -> None:
        """Check the distribution directory structure."""
        check = ExecutableValidationResult("dist_directory_structure")
        dist_root = _project_root / "dist"

        if not dist_root.exists():
            check.passed = True  # Non-critical for development
            check.details = {
                "dist_directory_exists": False,
                "note": "No dist/ directory — expected in development mode",
            }
            self._checks.append(check)
            self._print_check(check)
            return

        try:
            dist_contents = []
            for item in dist_root.iterdir():
                if item.is_dir():
                    sub_items = [str(s.relative_to(item)) for s in item.iterdir()][:20]
                    dist_contents.append({
                        "type": "directory",
                        "name": item.name,
                        "size_bytes": sum(
                            f.stat().st_size for f in item.rglob("*") if f.is_file()
                        ) if item.is_dir() else 0,
                        "contents": sub_items,
                    })
                else:
                    dist_contents.append({
                        "type": "file",
                        "name": item.name,
                        "size_bytes": item.stat().st_size,
                    })

            check.passed = True
            check.details = {
                "dist_directory_exists": True,
                "total_items": len(dist_contents),
                "contents": dist_contents,
            }
        except Exception as e:
            check.error = f"Dist directory scan failed: {e}"
            check.details = {"error": str(e)}

        self._checks.append(check)
        self._print_check(check)

    def _print_check(self, check: ExecutableValidationResult) -> None:
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
        print(f"{BOLD}Executable Validation Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Total checks: {total}")
        print(f"  Passed:       {GREEN}{passed}{RESET}")
        print(f"  Failed:       {RED}{total - passed}{RESET}")
        print(f"  Duration:     {total_duration:.0f}ms")
        if passed == total:
            print(f"\n{GREEN}{BOLD}  ALL EXECUTABLE VALIDATIONS PASSED{RESET}")
        else:
            print(f"\n{RED}{BOLD}  SOME VALIDATIONS FAILED{RESET}")
        print()

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete validation report."""
        passed = sum(1 for c in self._checks if c.passed)
        total = len(self._checks)

        return {
            "executable_validation_report": {
                "tool": "executable_validator.py",
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
    """Run the executable validator."""
    validator = ExecutableValidator()
    report = validator.run_all()

    report_dir = _project_root / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "executable_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved to: {report_path}")

    passed = report["executable_validation_report"]["passed"]
    total = report["executable_validation_report"]["total_checks"]
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
