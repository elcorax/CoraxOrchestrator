#!/usr/bin/env python3
"""
Corax Orchestrator - Developer Tools Bootstrap Script.

Standalone script to deploy developer tools (Git, Python, Node.js)
without needing the full Corax CLI.

Usage:
    python scripts/deploy_dev_tools.py
    python scripts/deploy_dev_tools.py --tools git,python
    python scripts/deploy_dev_tools.py --detect-only
    python scripts/deploy_dev_tools.py --validate-only
    python scripts/deploy_dev_tools.py --parallel
"""

import asyncio
import sys
import os
from pathlib import Path


# Ensure the project root is in the Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def main() -> None:
    """Run the dev tool deployment."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy developer tools (Git, Python, Node.js)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/deploy_dev_tools.py
  python scripts/deploy_dev_tools.py --tools git,python
  python scripts/deploy_dev_tools.py --detect-only
  python scripts/deploy_dev_tools.py --validate-only
  python scripts/deploy_dev_tools.py --parallel
  python scripts/deploy_dev_tools.py --no-skip-existing
        """,
    )

    parser.add_argument(
        "--tools",
        type=str,
        default="git,python,nodejs",
        help="Comma-separated list of tools to install (default: git,python,nodejs)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip already-installed tools (default: true)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Reinstall even if already installed",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run independent tools in parallel",
    )
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="Only detect installed tools, do not install",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate environment, do not install",
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Directory to save deployment reports",
    )

    args = parser.parse_args()

    # Setup logging
    from src.core.logging import setup_logging
    setup_logging()

    from src.deployment.dev_deploy import DevDeploy

    dev_deploy = DevDeploy(report_dir=args.report_dir)

    if args.detect_only:
        print("Detecting installed developer tools...")
        print()
        results = await dev_deploy.detect_all()
        for tool_key, result in results.items():
            status = "INSTALLED" if result.status.value == "installed" else "NOT FOUND"
            version = f" v{result.version}" if result.version else ""
            print(f"  {tool_key:10s} {status}{version}")
        return

    if args.validate_only:
        print("Validating environment...")
        print()
        validation = await dev_deploy.validate_environment()
        print(f"  All required: {validation.all_required_installed}")
        print(f"  All compatible: {validation.all_compatible}")
        print(f"  Score: {validation.score}/100")
        if validation.missing:
            print(f"  Missing: {', '.join(validation.missing)}")
        if validation.outdated:
            print(f"  Outdated: {', '.join(validation.outdated)}")
        if validation.warnings:
            for w in validation.warnings:
                print(f"  Warning: {w}")
        return

    tools = [t.strip() for t in args.tools.split(",") if t.strip()]

    print("=" * 60)
    print("  Corax Orchestrator - Developer Tools Deployment")
    print("=" * 60)
    print()
    print(f"  Tools: {', '.join(tools)}")
    print(f"  Skip existing: {args.skip_existing}")
    print(f"  Parallel: {args.parallel}")
    print()

    report = await dev_deploy.deploy(
        tools=tools,
        skip_existing=args.skip_existing,
        parallel=args.parallel,
    )

    print()
    print("=" * 60)
    print(f"  Status: {report.status.upper()}")
    print(f"  Duration: {report.duration_seconds:.1f}s")
    print(f"  Success rate: {report.success_rate:.0f}%")
    print()
    print(f"  Requested: {len(report.tools_requested)}")
    print(f"  Installed: {len(report.tools_installed)}")
    print(f"  Failed:    {len(report.tools_failed)}")
    print(f"  Skipped:   {len(report.tools_skipped)}")
    print()

    if report.tools_installed:
        print("  Successfully installed:")
        for tool in report.tools_installed:
            detail = report.tool_details.get(tool, {})
            version = detail.get("version_info", {}).get(
                f"{tool}_version", ""
            ) or detail.get("version", "")
            print(f"    ✓ {tool} {version}")

    if report.tools_failed:
        print("  Failed installations:")
        for tool in report.tools_failed:
            detail = report.tool_details.get(tool, {})
            error = detail.get("error", "Unknown error")
            print(f"    ✗ {tool}: {error}")

    if report.tools_skipped:
        print("  Skipped (already installed):")
        for tool in report.tools_skipped:
            print(f"    - {tool}")

    if report.errors:
        print()
        print("  Errors:")
        for error in report.errors:
            print(f"    ! {error}")

    print()
    if report.report_path:
        print(f"  Report saved to: {report.report_path}")
    print("=" * 60)

    # Return non-zero exit code if any tools failed
    if report.tools_failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
