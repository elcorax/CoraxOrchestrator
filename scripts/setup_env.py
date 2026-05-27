#!/usr/bin/env python3
"""
Corax Orchestrator - Environment Setup Script.

Bootstraps the Python environment with all required dependencies.
Handles virtual environment creation, package installation,
and optional platform-specific extras.

Usage:
    python scripts/setup_env.py                    # Core dependencies
    python scripts/setup_env.py --dev              # + dev dependencies
    python scripts/setup_env.py --all              # All optional deps
    python scripts/setup_env.py --windows          # + Windows extras
    python scripts/setup_env.py --check            # Check only, no install
"""

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parent.parent


def get_venv_python() -> str:
    """Get the Python executable path, preferring venv."""
    # Check if we're already in a venv
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_PREFIX")
    if venv:
        if sys.platform == "win32":
            return os.path.join(venv, "Scripts", "python.exe")
        return os.path.join(venv, "bin", "python")
    return sys.executable


def check_python_version() -> bool:
    """Check if Python version is sufficient."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"ERROR: Python 3.10+ required, found {version.major}.{version.minor}")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_pip() -> bool:
    """Check if pip is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"✓ pip: {result.stdout.strip().split()[1]}")
            return True
        print("✗ pip not available")
        return False
    except Exception as e:
        print(f"✗ pip check failed: {e}")
        return False


def check_venv() -> bool:
    """Check if running in a virtual environment."""
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print(f"✓ Virtual environment: {sys.prefix}")
    else:
        print("⚠ Not in a virtual environment (recommended)")
    return in_venv


def install_packages(packages: list[str], upgrade: bool = False) -> bool:
    """Install pip packages."""
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)

    print(f"  Installing: {' '.join(packages)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        return True
    print(f"  FAILED: {result.stderr.strip()[:200]}")
    return False


def check_import(module_name: str, package_name: str = None) -> bool:
    """Check if a Python module can be imported."""
    try:
        importlib.import_module(module_name)
        print(f"  ✓ {module_name}")
        return True
    except ImportError:
        pkg = package_name or module_name
        print(f"  ✗ {module_name} (install: pip install {pkg})")
        return False


def check_core_deps() -> dict[str, bool]:
    """Check core dependencies."""
    deps = {
        "yaml": ("yaml", "pyyaml"),
        "psutil": ("psutil",),
        "platformdirs": ("platformdirs",),
        "aiohttp": ("aiohttp",),
        "httpx": ("httpx",),
        "aiofiles": ("aiofiles",),
        "orjson": ("orjson",),
        "structlog": ("structlog",),
        "rich": ("rich",),
        "click": ("click",),
    }
    results = {}
    for name, (mod, *_) in deps.items():
        results[name] = check_import(mod)
    return results


def check_optional_deps() -> dict[str, bool]:
    """Check optional dependencies."""
    deps = {
        "msgpack": ("msgpack",),
        "wmi": ("wmi",),
        "huggingface_hub": ("huggingface_hub", "huggingface-hub"),
        "distro": ("distro",),
    }
    results = {}
    for name, (mod, *_) in deps.items():
        results[name] = check_import(mod)
    return results


def check_dev_deps() -> dict[str, bool]:
    """Check development dependencies."""
    deps = {
        "pytest": ("pytest",),
        "pytest_asyncio": ("pytest_asyncio", "pytest-asyncio"),
        "pytest_cov": ("pytest_cov", "pytest-cov"),
        "pytest_mock": ("pytest_mock", "pytest-mock"),
        "mypy": ("mypy",),
        "ruff": ("ruff",),
    }
    results = {}
    for name, (mod, *_) in deps.items():
        results[name] = check_import(mod)
    return results


def check_tools() -> dict[str, bool]:
    """Check if required system tools are available."""
    tools = ["git", "winget", "python", "node", "npm"]
    results = {}
    for tool in tools:
        found = bool(importlib.util.find_spec("shutil"))
        if found:
            import shutil
            path = shutil.which(tool)
            results[tool] = path is not None
            if path:
                print(f"  ✓ {tool}: {path}")
            else:
                print(f"  ✗ {tool}: not found in PATH")
        else:
            results[tool] = False
            print(f"  ? {tool}: cannot check")
    return results


def run_check(args: argparse.Namespace) -> int:
    """Run environment check."""
    print("\n" + "=" * 60)
    print("CORAX ORCHESTRATOR - ENVIRONMENT CHECK")
    print("=" * 60)

    print("\n[1/6] Python Version:")
    check_python_version()

    print("\n[2/6] Virtual Environment:")
    check_venv()

    print("\n[3/6] pip:")
    check_pip()

    print("\n[4/6] Core Dependencies:")
    core = check_core_deps()

    if args.all or args.windows:
        print("\n[5/6] Optional Dependencies:")
        check_optional_deps()

    if args.dev:
        print("\n[5/6] Development Dependencies:")
        check_dev_deps()

    print("\n[6/6] System Tools:")
    check_tools()

    # Summary
    print("\n" + "=" * 60)
    missing = [k for k, v in core.items() if not v]
    if missing:
        print(f"⚠ Missing core deps: {', '.join(missing)}")
        print("  Run: python scripts/setup_env.py")
        return 1
    print("✓ All core dependencies satisfied")
    return 0


def run_install(args: argparse.Namespace) -> int:
    """Run package installation."""
    print("\n" + "=" * 60)
    print("CORAX ORCHESTRATOR - INSTALLING DEPENDENCIES")
    print("=" * 60)

    # Core packages
    core_packages = [
        "pyyaml>=6.0.1",
        "psutil>=5.9.8",
        "platformdirs>=4.2.0",
        "aiohttp>=3.9.3",
        "httpx>=0.27.0",
        "aiofiles>=23.2.1",
        "orjson>=3.9.13",
        "structlog>=24.1.0",
        "rich>=13.7.1",
        "click>=8.1.7",
    ]

    print("\n[1/3] Installing core dependencies...")
    if not install_packages(core_packages):
        print("FAILED: Core dependency installation")
        return 1

    # Optional packages
    if args.all or args.windows:
        print("\n[2/3] Installing Windows-specific dependencies...")
        windows_packages = ["pywin32>=306", "wmi>=1.5.1"]
        install_packages(windows_packages)

    if args.all:
        print("\n[2/3] Installing optional dependencies...")
        optional_packages = ["msgpack>=1.0.8", "huggingface-hub>=0.22.0", "distro>=1.9.0"]
        install_packages(optional_packages)

    # Dev packages
    if args.dev or args.all:
        print("\n[3/3] Installing development dependencies...")
        dev_packages = [
            "pytest>=8.0.2",
            "pytest-asyncio>=0.23.5",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.12.0",
            "mypy>=1.8.0",
            "ruff>=0.2.2",
        ]
        if not install_packages(dev_packages):
            print("WARNING: Some dev dependencies failed")

    print("\n✓ Installation complete")
    print("  Run validation: python _validate.py")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator - Environment Setup",
    )
    parser.add_argument("--check", action="store_true", help="Check environment only")
    parser.add_argument("--dev", action="store_true", help="Include dev dependencies")
    parser.add_argument("--all", action="store_true", help="Include all optional deps")
    parser.add_argument("--windows", action="store_true", help="Include Windows extras")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade packages")
    args = parser.parse_args()

    if args.check:
        return run_check(args)
    return run_install(args)


if __name__ == "__main__":
    sys.exit(main())
