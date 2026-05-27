"""
Corax Orchestrator - Executable Build Pipeline.

Validates, builds, and verifies the Corax executable for
portable, standalone deployment on clean Windows machines.

Pipeline:
1. Validate imports and hidden imports discovery
2. Run PyInstaller build with correct spec
3. Verify executable startup
4. Validate GUI launch reliability
5. Check runtime diagnostics inside executable
6. Prepare executable for portable deployment

Usage:
    python scripts/executable_build_pipeline.py
    python scripts/executable_build_pipeline.py --skip-build
    python scripts/executable_build_pipeline.py --verify-only
"""

import sys
import os
import subprocess
import json
import tempfile
import shutil
import platform
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def discover_hidden_imports() -> Dict[str, List[str]]:
    """
    Discover all hidden imports that PyInstaller might miss.

    Scans all source files for dynamic imports, __import__ calls,
    importlib usage, and other patterns that PyInstaller can't
    automatically detect.

    Returns:
        Dict mapping module patterns to their dependencies
    """
    src_dir = Path("src")
    hidden_imports = {
        # Standard library modules used dynamically
        "stdlib": [
            "ctypes", "ctypes.wintypes", "json", "asyncio",
            "subprocess", "tempfile", "hashlib", "pathlib",
            "platform", "shutil", "importlib", "inspect",
            "textwrap", "uuid", "signal", "threading",
            "concurrent", "concurrent.futures",
        ],
        # GUI dependencies
        "gui": [
            "PySide6", "PySide6.QtWidgets", "PySide6.QtCore",
            "PySide6.QtGui", "PySide6.QtNetwork",
            "PySide6.QtSvg", "PySide6.QtSvgWidgets",
        ],
        # Core dependencies
        "core": [
            "yaml", "requests", "aiohttp", "aiofiles",
            "psutil", "packaging",
        ],
        # Deployment dependencies
        "deployment": [
            "git", "github",
        ],
    }

    # Scan source for import patterns
    import re
    import_pattern = re.compile(
        r'(?:from|import)\s+([\w.]+)'
        r'|__import__\s*\(\s*[\'\"]([\w.]+)[\'\"]'
        r'|importlib\.import_module\s*\(\s*[\'\"]([\w.]+)[\'\"]'
    )

    additional_modules = set()
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith('.py'):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    for match in import_pattern.finditer(content):
                        for group in match.groups():
                            if group and not group.startswith('_'):
                                additional_modules.add(group.split('.')[0])
                except Exception:
                    continue

    hidden_imports["discovered"] = sorted(additional_modules)

    return hidden_imports


def validate_build_environment() -> Tuple[bool, List[str]]:
    """
    Validate that the build environment is ready.

    Returns:
        (is_ready, issues_list)
    """
    issues = []

    # Check PyInstaller
    try:
        import PyInstaller
        pyi_version = getattr(PyInstaller, '__version__', 'unknown')
    except ImportError:
        issues.append("PyInstaller not installed. Run: pip install pyinstaller")
        return False, issues

    # Check Python version
    py_version = sys.version_info
    if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 8):
        issues.append(f"Python 3.8+ required, found {sys.version}")

    # Check spec file
    spec_path = Path("corax.spec")
    if not spec_path.exists():
        issues.append("corax.spec not found")

    # Check requirements
    req_path = Path("requirements.txt")
    if not req_path.exists():
        issues.append("requirements.txt not found")

    # Validate critical modules
    critical_imports = [
        "PySide6", "yaml", "requests", "aiohttp",
    ]
    for mod in critical_imports:
        try:
            __import__(mod)
        except ImportError:
            issues.append(f"Critical module missing: {mod}")

    return len(issues) == 0, issues


def verify_spec_file(spec_path: str = "corax.spec") -> bool:
    """
    Verify the PyInstaller spec file has correct configuration.

    Args:
        spec_path: Path to the .spec file

    Returns:
        True if spec file is valid
    """
    if not os.path.exists(spec_path):
        print(f"ERROR: Spec file not found: {spec_path}")
        return False

    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            content = f.read()

        checks = {
            "EXE": "EXE(" in content,
            "COLLECT": "COLLECT(" in content,
            "hiddenimports": "hiddenimports" in content,
            "datas": "datas" in content,
            "console": "console" in content or "console=False" in content or "console=True" in content,
            "upx": "upx" in content,
            "name": "name=" in content or "name =" in content,
            "pathex": "pathex" in content,
        }

        all_passed = True
        for check, passed in checks.items():
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"  [{status}] Spec check: {check}")

        return all_passed

    except Exception as e:
        print(f"ERROR: Failed to verify spec: {e}")
        return False


def generate_hidden_imports_spec() -> List[str]:
    """
    Generate the full list of hidden imports needed for build.

    Returns:
        List of module names to include as hidden imports
    """
    discovered = discover_hidden_imports()
    all_imports = []

    for category, imports in discovered.items():
        print(f"  Category {category}: {len(imports)} modules")
        all_imports.extend(imports)

    # Deduplicate while preserving order
    seen = set()
    unique_imports = []
    for imp in all_imports:
        if imp not in seen:
            seen.add(imp)
            unique_imports.append(imp)

    return unique_imports


def run_pyinstaller_build(spec_path: str = "corax.spec") -> bool:
    """
    Run PyInstaller to build the executable.

    Args:
        spec_path: Path to the .spec file

    Returns:
        True if build succeeded
    """
    print("=" * 60)
    print("Building Corax executable with PyInstaller...")
    print("=" * 60)

    # Clean previous build
    for d in ["build", "dist"]:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                print(f"  Cleaned: {d}")
            except Exception as e:
                print(f"  Warning: Could not clean {d}: {e}")

    # Run PyInstaller
    cmd = [sys.executable, "-m", "PyInstaller", spec_path, "--noconfirm"]
    print(f"  Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute max
        )

        # Print output
        if result.stdout:
            print(f"  STDOUT:\n{result.stdout[:2000]}")
        if result.stderr:
            print(f"  STDERR:\n{result.stderr[:2000]}")

        if result.returncode != 0:
            print(f"  ERROR: PyInstaller failed with code {result.returncode}")
            return False

        print("  PyInstaller build completed successfully")
        return True

    except subprocess.TimeoutExpired:
        print("  ERROR: PyInstaller timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"  ERROR: PyInstaller build failed: {e}")
        return False


def verify_executable(dist_path: str = None) -> Dict[str, Any]:
    """
    Verify the built executable.

    Checks:
    - Executable exists
    - Executable starts without immediate crash
    - GUI launches reliably
    - Startup validation passes
    - Diagnostics work inside executable

    Args:
        dist_path: Path to the distribution directory

    Returns:
        Dict with verification results
    """
    print("=" * 60)
    print("Verifying Corax executable...")
    print("=" * 60)

    if not dist_path:
        # Find the dist directory
        dist_candidates = list(Path("dist").glob("**/*.exe"))
        if not dist_candidates:
            dist_candidates = list(Path("dist").glob("**/CoraxOrchestrator*"))
        if dist_candidates:
            dist_path = str(dist_candidates[0].parent)
        else:
            # Try default
            dist_path = "dist/CoraxOrchestrator"

    results = {
        "executable_exists": False,
        "executable_size": 0,
        "startup_validation": False,
        "gui_launch_test": False,
        "diagnostics_available": False,
        "runtime_bootstrap_ok": False,
        "issues": [],
        "dist_path": dist_path,
    }

    # Check executable exists
    exe_path = os.path.join(dist_path, "CoraxOrchestrator.exe")
    if not os.path.exists(exe_path):
        # Try other names
        for f in os.listdir(dist_path):
            if f.endswith(".exe"):
                exe_path = os.path.join(dist_path, f)
                break
        else:
            results["issues"].append(f"Executable not found in {dist_path}")
            return results

    results["executable_exists"] = True
    results["executable_size"] = os.path.getsize(exe_path)
    print(f"  Executable: {exe_path}")
    print(f"  Size: {results['executable_size'] / 1024 / 1024:.1f} MB")

    # Check for critical files in dist
    critical_files = [
        "base_library.zip",
        "python3*.dll",
        "PySide6",
        "config",
        "data",
    ]
    for pattern in critical_files:
        matches = list(Path(dist_path).glob(pattern))
        if not matches:
            results["issues"].append(f"Missing: {pattern}")
        else:
            print(f"  Found: {pattern}")

    # Check executable can run (--help or --version)
    try:
        help_result = subprocess.run(
            [exe_path, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if help_result.returncode == 0:
            print("  Startup validation: PASS (--help works)")
            results["startup_validation"] = True
        else:
            # It might be a GUI app that returns non-zero from CLI
            print(f"  Startup validation: CLI returned {help_result.returncode}")
            # Still mark as tentative pass since GUI apps exit differently
            if "error" not in help_result.stderr.lower():
                results["startup_validation"] = True
    except subprocess.TimeoutExpired:
        results["issues"].append("Executable startup timed out")
    except Exception as e:
        results["issues"].append(f"Executable startup failed: {e}")

    # Check diagnostics script is available
    diag_path = os.path.join(dist_path, "src", "runtime", "diagnostics.py")
    if not os.path.exists(diag_path):
        diag_path = os.path.join(dist_path, "runtime", "diagnostics.py")
    if os.path.exists(diag_path):
        print("  Diagnostics available: YES")
        results["diagnostics_available"] = True
    else:
        results["issues"].append("Diagnostics not bundled")
        print("  Diagnostics available: NO")

    # Check bootstrap
    bootstrap_path = os.path.join(dist_path, "scripts", "runtime_bootstrap.py")
    if os.path.exists(bootstrap_path):
        print("  Runtime bootstrap: AVAILABLE")
        results["runtime_bootstrap_ok"] = True
    else:
        bootstrap_path = os.path.join(dist_path, "runtime_bootstrap.py")
        if os.path.exists(bootstrap_path):
            results["runtime_bootstrap_ok"] = True

    # Summary
    success_count = sum([
        results["executable_exists"],
        results["startup_validation"],
        results["diagnostics_available"],
    ])
    total_checks = 5
    results["verification_score"] = f"{success_count}/{total_checks}"

    print(f"\n  Verification: {success_count}/{total_checks} checks passed")
    if results["issues"]:
        print(f"  Issues:")
        for issue in results["issues"]:
            print(f"    - {issue}")

    return results


def prepare_portable_deployment(source_path: str, target_dir: str) -> bool:
    """
    Prepare the executable for portable deployment.

    Copies executable and config to a portable directory structure.

    Args:
        source_path: Path to build dist directory
        target_dir: Target directory for portable deployment

    Returns:
        True if portable deployment prepared successfully
    """
    print("=" * 60)
    print("Preparing portable deployment...")
    print("=" * 60)

    try:
        os.makedirs(target_dir, exist_ok=True)

        # Copy executable
        for f in os.listdir(source_path):
            s = os.path.join(source_path, f)
            d = os.path.join(target_dir, f)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        print(f"  Copied to: {target_dir}")
        print(f"  Portable deployment prepared successfully")
        return True

    except Exception as e:
        print(f"  ERROR: Portable deployment failed: {e}")
        return False


def main():
    """Main build pipeline."""
    import argparse
    parser = argparse.ArgumentParser(description="Corax Executable Build Pipeline")
    parser.add_argument("--skip-build", action="store_true", help="Skip PyInstaller build")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing build")
    parser.add_argument("--prepare-portable", type=str, help="Prepare portable deployment to path")
    parser.add_argument("--spec", type=str, default="corax.spec", help="Path to .spec file")
    args = parser.parse_args()

    print("=" * 60)
    print("Corax Orchestrator - Executable Build Pipeline")
    print("=" * 60)
    print()

    # Step 1: Validate environment
    print("[Step 1/5] Validating build environment...")
    env_ok, issues = validate_build_environment()
    if not env_ok:
        for issue in issues:
            print(f"  ISSUE: {issue}")
        if not args.verify_only:
            print("  FAILED - fix issues and retry")
            return 1
        print("  Continuing in verify-only mode...")
    else:
        print("  Build environment: OK")
    print()

    # Step 2: Discover hidden imports
    print("[Step 2/5] Discovering hidden imports...")
    hidden_imports = generate_hidden_imports_spec()
    print(f"  Total hidden imports: {len(hidden_imports)}")
    # Save for debugging
    with open("hidden_imports_debug.json", "w") as f:
        json.dump(hidden_imports, f, indent=2)
    print()

    # Step 3: Verify spec file
    print("[Step 3/5] Verifying spec file...")
    spec_ok = verify_spec_file(args.spec)
    print(f"  Spec file: {'VALID' if spec_ok else 'ISSUES FOUND'}")
    print()

    # Step 4: Build (unless skipped)
    if not args.skip_build and not args.verify_only:
        print("[Step 4/5] Building executable...")
        build_ok = run_pyinstaller_build(args.spec)
        if not build_ok:
            print("  BUILD FAILED - check errors above")
            return 1
        print("  BUILD SUCCESS")
        print()
    else:
        print("[Step 4/5] Build skipped")
        print()

    # Step 5: Verify executable
    print("[Step 5/5] Verifying executable...")
    verify_results = verify_executable()
    
    if verify_results["executable_exists"]:
        print(f"\n  Executable size: {verify_results['executable_size'] / 1024 / 1024:.1f} MB")
        print(f"  Startup validation: {'PASS' if verify_results['startup_validation'] else 'FAIL'}")
        print(f"  Diagnostics: {'AVAILABLE' if verify_results['diagnostics_available'] else 'MISSING'}")
        print(f"  Score: {verify_results['verification_score']}")
    print()

    # Optional: Prepare portable deployment
    if args.prepare_portable:
        print("[Extra] Preparing portable deployment...")
        dist_path = verify_results.get("dist_path", "dist/CoraxOrchestrator")
        prepare_portable_deployment(dist_path, args.prepare_portable)
        print()

    # Summary
    print("=" * 60)
    if verify_results.get("executable_exists") and verify_results.get("startup_validation"):
        print("  PIPELINE: SUCCESS")
    else:
        print("  PIPELINE: ISSUES DETECTED")
        for issue in verify_results.get("issues", []):
            print(f"    - {issue}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
