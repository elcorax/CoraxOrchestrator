"""
Corax Orchestrator - Main Entry Point.

Launches the GUI application with runtime kernel initialization,
RuntimeBridge convergence, environment validation, and startup diagnostics.

Convergence Flow:
1. Initialize kernel → CoraxRuntimeKernel.start()
2. Push kernel state → RuntimeBridge → UIStateManager
3. Launch GUI → MainWindow reads UIStateManager
4. Start bridge loop → Live sync between Runtime and GUI

Usage:
    python -m src.main
    corax.exe (packaged)
"""

import sys
import os
import traceback
import asyncio


def main():
    """Main entry point for Corax Orchestrator."""
    # Ensure src is on path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    # Run startup diagnostics
    try:
        from src.health.self_setup import SelfSetup
        setup = SelfSetup()
        setup.validate_environment()
    except Exception as e:
        print(f"[Corax] Startup validation warning: {e}")

    # Portable environment detection and preparation
    try:
        from src.deployment.portable import PortableDeployment
        portable = PortableDeployment()
        if portable.is_portable:
            print(f"[Corax] Running in portable mode (root: {portable.root_path})")
            portable.setup_environment()
        else:
            # Still ensure directories exist
            portable._create_data_directories()
    except Exception as e:
        print(f"[Corax] Portable env prep warning: {e}")

    # Restore-point detection and recovery
    try:
        from src.deployment.restore.windows_restore import (
            WindowsRestorePoint,
        )
        restore = WindowsRestorePoint()
        if sys.platform == "win32":
            status = restore.get_status_report()
            if status.get("is_admin") and status.get("system_restore_available"):
                print("[Corax] System Restore available - protect before deployment")
            elif not status.get("is_admin"):
                print("[Corax] Not running as admin - restore points unavailable")
    except ImportError:
        pass  # Windows-only module
    except Exception as e:
        print(f"[Corax] Restore point check warning: {e}")


    # Initialize and run GUI with full convergence
    try:
        from src.gui.application import CoraxApplication
        app = CoraxApplication()

        if app.initialize():
            # Start the kernel → bridge → GUI convergence
            app.start_convergence()

            exit_code = app.run()
            sys.exit(exit_code)
        else:
            print("[Corax] Failed to initialize application")
            sys.exit(1)
    except ImportError as e:
        print(f"[Corax] Import error: {e}")
        print("[Corax] Missing dependencies. Run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"[Corax] Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
